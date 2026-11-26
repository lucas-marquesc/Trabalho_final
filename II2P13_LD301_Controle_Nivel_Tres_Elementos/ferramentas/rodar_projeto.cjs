// Roda um projeto .lsproj da II2P13 no Core REAL do LasecSimul, sem o VS Code (headless).
//
//   node ferramentas/rodar_projeto.cjs <projeto.lsproj> <roteiro.json> [saida.json]
//
// O roteiro diz quanto simular, o que ler e o que mudar no caminho:
//   { "duracao": 300, "periodo": 1,
//     "ler": { "nivel": "planta:nivel_pct", "qfw": "planta:qfw", "ao": "clp:AO_FV102", "pos": "fy:pos" },
//     "eventos": [ { "t": 60, "planta": { "c_demanda": 80 } }, { "t": 100, "clp": { "MODO_AUTO": "TRUE" } } ] }
// Fontes de leitura: planta:<id interno do subsistema>, fy:<id interno do FY301>, clp:<variável do MAIN>.
// Os modems HART ficam desligados (auto_open = false): nenhuma porta COM é aberta.
//
// Usa os módulos da extensão LasecSimul: LASECSIMUL_EXT (padrão: o repositório de desenvolvimento,
// senão a extensão instalada mais nova).
const fs = require("fs");
const os = require("os");
const path = require("path");

function extensao() {
  if (process.env.LASECSIMUL_EXT) return process.env.LASECSIMUL_EXT;
  const dev = "C:/SourceCode/LasecSimul/extension";
  if (fs.existsSync(path.join(dev, "out", "ipc", "CoreClient.js"))) return dev;
  const base = path.join(os.homedir(), ".vscode", "extensions");
  const instaladas = fs.readdirSync(base).filter((n) => n.startsWith("josuemoraisgh.lasecsimul-")).sort().reverse();
  if (!instaladas.length) throw new Error("Extensão LasecSimul não encontrada");
  return path.join(base, instaladas[0]);
}
const EXT = extensao();
const OUT = path.join(EXT, "out");
const req = (m) => require(path.join(OUT, m));
const { CoreProcess } = req("ipc/CoreProcess");
const { CoreClient } = req("ipc/CoreClient");
const { resolveCoreExecutablePath } = req("core/coreExecutable");
const { materializeEmbeddedSubcircuit } = req("project/embeddedSubcircuits");
const { buildOpenPlcProject } = req("plc/openplc/openPlcBuild.js");
const { resolvePlcToolchain } = req("plc/plcBuild.js");
const { loadOpenPlcHost } = req("plc/openplc/openPlcHost.js");
const REPO = path.resolve(EXT, "..");
const BIBLIOTECA = fs.existsSync(path.join(REPO, "subcircuits", "library.json"))
  ? path.join(REPO, "subcircuits", "library.json") : path.join(EXT, "bundled", "subcircuits", "library.json");

// Pinos dos componentes do painel (o Core escolhe os terminais pelo nome)
const PINOS = {
  "sources.dc_voltage": ["pin-1", "pin-2"], "other.ground": ["pin"], "meters.ampmeter": ["pin-1", "pin-2"],
  "passive.resistor": ["pin-1", "pin-2"], "passive.capacitor": ["pin-1", "pin-2"], "connectors.tunnel": ["pin"],
  "protocol.hart.modem": ["loop_plus", "loop_minus"], "bridges.voltage_sensor": ["value", "p", "n"],
  "bridges.controlled_current_source": ["command", "p", "n"], "bridges.controlled_voltage_source": ["command", "p", "n"],
  "sl.fcn": ["in1", "out1"],
};

/** Toolchain do CLP (STruC++ + g++): a da extensão escolhida ou, se o g++ dela não existir (repositório de
 * desenvolvimento sem o MSYS2), a da extensão instalada mais nova. */
function toolchainClp() {
  // primeiro o toolchain empacotado das extensões instaladas (o mesmo dos alunos), depois o da escolhida
  const candidatas = [];
  const base = path.join(os.homedir(), ".vscode", "extensions");
  if (fs.existsSync(base)) {
    for (const n of fs.readdirSync(base).filter((n) => n.startsWith("josuemoraisgh.lasecsimul-")).sort().reverse()) candidatas.push(path.join(base, n));
  }
  candidatas.push(EXT);
  for (const ext of candidatas) {
    const t = resolvePlcToolchain(ext);
    const gpp = t.cxxCompiler;
    if (!gpp || fs.existsSync(gpp)) return { ext, toolchain: t };
  }
  return { ext: EXT, toolchain: resolvePlcToolchain(EXT) };
}

async function construirClp(lsplc, storage) {
  const { ext, toolchain } = toolchainClp();
  const host = loadOpenPlcHost({ extensionPath: ext, storageDir: storage, toolchain });
  const r = await buildOpenPlcProject(lsplc, { toolchain, cacheRoot: path.join(storage, "plc-builds"), host, log: () => {} });
  if (!r.ok) throw new Error(`CLP não compilou: ${r.log}`);
  return r;
}

async function carregarProjeto(client, arquivo, storage) {
  const doc = JSON.parse(fs.readFileSync(arquivo, "utf8"));
  for (const def of doc.subsystems ?? []) await client.registerAdhocSubcircuitDefinition(materializeEmbeddedSubcircuit(def), { replace: true });
  const ids = new Map();
  const fronteira = new Map();
  let clp;
  for (const c of doc.components) {
    if (c.typeId.startsWith("graphics.")) continue;
    const props = Object.fromEntries(Object.entries(c.properties ?? {}).filter(([k]) => !k.startsWith("@") && !k.startsWith("__ui_")));
    if (c.typeId === "protocol.hart.modem") props.auto_open = false;
    let pins = (PINOS[c.typeId] ?? []).map((id, i) => ({ id, x: 0, y: i * 10 }));
    if (c.typeId === "plc.instance") pins = c.plc.exportedIo.map((io, i) => ({ id: io.ioId, x: 0, y: i * 12 }));
    if (c.typeId === "subcircuits.hart.smar_fy301") pins = ["supply", "out1", "position", "loop_plus", "loop_minus"].map((id, i) => ({ id, x: 0, y: i * 12 }));
    if (c.typeId === "subcircuits.hart.smar_ld301") pins = ["high", "low", "loop_plus", "loop_minus"].map((id, i) => ({ id, x: 0, y: i * 12 }));
    const r = await client.addComponent(c.typeId, props, pins, c.id);
    ids.set(c.id, r.instanceId);
    fronteira.set(c.id, { ...(r.exposedPins ?? {}), ...(r.exposedSignalPins ?? {}) });
    for (const [k, v] of Object.entries(c.properties ?? {})) {
      if (!k.startsWith("@")) continue;
      const [filho, nome] = k.slice(1).split(/\.(.+)/);
      await client.setSubcircuitChildProperty(r.instanceId, filho, nome, v);
    }
    if (c.typeId === "connectors.tunnel") await client.setTunnelName(r.instanceId, "pin", "", String(c.properties.name));
    if (c.typeId === "plc.instance") {
      // os pinos do CLP vêm do programa: carregar o build antes de ligar os fios
      clp = { id: c.id, instanceId: r.instanceId, ref: path.resolve(path.dirname(arquivo), c.plc.iecProjectRef) };
      const build = await construirClp(clp.ref, storage);
      await client.setPlcTaskInterval(clp.instanceId, Math.round(build.entry.taskIntervalMs * 1e6));
      await client.loadPlcArtifact(clp.instanceId, build.module);
      clp.programa = build.entry.programName;
    }
  }
  const ponta = (cid, pino) => fronteira.get(cid)?.[pino] ?? { instanceId: ids.get(cid), pinId: pino };
  for (const w of doc.topology.conductors) {
    if (!ids.has(w.from.componentId) || !ids.has(w.to.componentId)) continue;
    const a = ponta(w.from.componentId, w.from.pinId);
    const b = ponta(w.to.componentId, w.to.pinId);
    await client.connectWire(a.instanceId, a.pinId, b.instanceId, b.pinId);
  }
  return { doc, ids, clp };
}

async function main() {
  const [arquivo, roteiroArq, saida] = process.argv.slice(2);
  const roteiro = JSON.parse(fs.readFileSync(roteiroArq, "utf8"));
  const storage = path.join(os.tmpdir(), "ii2p13-rodar");
  const pipeName = `ii2p13-rodar-${process.pid}`;
  const pm = new CoreProcess({ executablePath: resolveCoreExecutablePath(EXT), pipeName });
  const client = new CoreClient(pipeName, { requestTimeoutMs: 120000 });
  pm.start();
  await client.start();
  const resultado = { projeto: arquivo, amostras: [] };
  try {
    await client.loadDeviceLibrary(BIBLIOTECA);
    const { ids, clp } = await carregarProjeto(client, path.resolve(arquivo), storage);
    const filho = new Map();
    const idFilho = async (dono, local) => {
      const k = `${dono}|${local}`;
      if (!filho.has(k)) filho.set(k, await client.getSubcircuitChildInstanceId(ids.get(dono), local));
      return filho.get(k);
    };
    const DONO = { planta: "ii2p13-planta", fy: "ii2p13-fy-102" };
    // resolve os ids antes de rodar
    for (const fonte of Object.values(roteiro.ler)) {
      const [tipo, nome] = fonte.split(":");
      if (DONO[tipo]) await idFilho(DONO[tipo], nome);
    }
    const ler = async () => {
      const out = {};
      for (const [rotulo, fonte] of Object.entries(roteiro.ler)) {
        const [tipo, nome] = fonte.split(":");
        try {
          if (tipo === "clp") {
            const txt = await client.plcGet(clp.instanceId, `${clp.programa}.${nome}`);
            const v = txt.split("=").pop().trim().split(" ")[0];
            out[rotulo] = v === "TRUE" ? 1 : v === "FALSE" ? 0 : Number(v);
          } else {
            out[rotulo] = (await client.getComponentState(await idFilho(DONO[tipo], nome))).readDoubleLE(0);
          }
        } catch (e) { out[rotulo] = null; }
      }
      return out;
    };
    const eventos = [...(roteiro.eventos ?? [])].sort((a, b) => a.t - b.t);
    const periodo = roteiro.periodo ?? 1;
    let t = 0;
    while (t < roteiro.duracao - 1e-9) {
      while (eventos.length && eventos[0].t <= t + 1e-9) {
        const ev = eventos.shift();
        for (const [k, v] of Object.entries(ev.planta ?? {})) await client.setSubcircuitChildProperty(ids.get("ii2p13-planta"), k, "value", v);
        for (const [k, v] of Object.entries(ev.clp ?? {})) await client.plcForce(clp.instanceId, `${clp.programa}.${k}`, String(v));
        for (const k of ev.soltar ?? []) await client.plcUnforce(clp.instanceId, `${clp.programa}.${k}`);
      }
      await client.step(Math.round(periodo * 1e9));
      t += periodo;
      resultado.amostras.push({ t: Math.round(t * 1000) / 1000, ...(await ler()) });
    }
  } finally {
    await client.stop().catch(() => undefined);
    pm.kill();
  }
  const texto = JSON.stringify(resultado, null, 1);
  if (saida) fs.writeFileSync(saida, texto); else console.log(texto);
}

main().catch((e) => { console.error("ERRO", e); process.exit(1); });
