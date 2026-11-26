// Compila um projeto de CLP (.lsplc) como o LasecSimul e o executa no CLP do Core com entradas forçadas.
//
//   node ferramentas/testar_clp.cjs <projeto.lsplc> <vetores.json>
//
// vetores.json: { "ler": ["NIVEL", ...], "casos": [ { "nome": "...", "segundos": 0.5, "entradas": { "AI_LT101": 3.0 } } ] }
// Saída (stdout, JSON): { ok, linguagens: {POU: linguagem}, erros, casos: [ { nome, lidos: {VAR: número | null} } ] }
const fs = require("fs");
const os = require("os");
const path = require("path");

function extensoes() {
  const lista = [];
  if (process.env.LASECSIMUL_EXT) lista.push(process.env.LASECSIMUL_EXT);
  const dev = "C:/SourceCode/LasecSimul/extension";
  if (fs.existsSync(path.join(dev, "out", "ipc", "CoreClient.js"))) lista.push(dev);
  const base = path.join(os.homedir(), ".vscode", "extensions");
  if (fs.existsSync(base)) {
    for (const n of fs.readdirSync(base).filter((n) => n.startsWith("josuemoraisgh.lasecsimul-")).sort().reverse()) lista.push(path.join(base, n));
  }
  if (!lista.length) throw new Error("Extensão LasecSimul não encontrada");
  return lista;
}
const EXTS = extensoes();
const EXT = EXTS[0];
const req = (m) => require(path.join(EXT, "out", m));
const { CoreProcess } = req("ipc/CoreProcess");
const { CoreClient } = req("ipc/CoreClient");
const { resolveCoreExecutablePath } = req("core/coreExecutable");
const { buildOpenPlcProject } = req("plc/openplc/openPlcBuild.js");
const { resolvePlcToolchain } = req("plc/plcBuild.js");
const { loadOpenPlcHost, loadLsplcProject } = req("plc/openplc/openPlcHost.js");

function toolchainClp() {
  // primeiro o toolchain empacotado das extensões instaladas (o mesmo dos alunos)
  const ordem = [...EXTS.filter((e) => e.includes(".vscode")), ...EXTS.filter((e) => !e.includes(".vscode"))];
  for (const ext of ordem) {
    const t = resolvePlcToolchain(ext);
    if (!t.cxxCompiler || fs.existsSync(t.cxxCompiler)) return { ext, toolchain: t };
  }
  return { ext: EXT, toolchain: resolvePlcToolchain(EXT) };
}

function numero(txt) {
  const v = String(txt).split("=").pop().trim().split(" ")[0];
  if (v === "TRUE") return 1;
  if (v === "FALSE") return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

(async () => {
  const [arquivo, vetoresArq] = process.argv.slice(2);
  const vetores = JSON.parse(fs.readFileSync(vetoresArq, "utf8"));
  const storage = path.join(os.tmpdir(), "ii2p13-testar-clp");
  const { ext, toolchain } = toolchainClp();
  const host = loadOpenPlcHost({ extensionPath: ext, storageDir: storage, toolchain });
  const saida = { ok: false, linguagens: {}, erros: [], casos: [] };
  try {
    const projeto = loadLsplcProject(host, path.resolve(arquivo));
    for (const pou of projeto.data.pous) saida.linguagens[pou.name] = String(pou.body?.language ?? "");
  } catch (e) { saida.erros.push(`leitura: ${e.message}`); }
  const r = await buildOpenPlcProject(path.resolve(arquivo), { toolchain, cacheRoot: path.join(storage, "plc-builds"), host, log: () => {} });
  if (!r.ok) {
    saida.erros.push(r.log);
    console.log(JSON.stringify(saida));
    return;
  }
  const pipeName = `ii2p13-testar-clp-${process.pid}`;
  const pm = new CoreProcess({ executablePath: resolveCoreExecutablePath(EXT), pipeName });
  const client = new CoreClient(pipeName, { requestTimeoutMs: 60000 });
  pm.start();
  await client.start();
  try {
    const pins = r.module.exportedIo.map((io, i) => ({ id: io.ioId, x: 0, y: i * 12 }));
    const plc = await client.addComponent("plc.instance", {}, pins, "CLP");
    await client.setPlcTaskInterval(plc.instanceId, Math.round(r.entry.taskIntervalMs * 1e6));
    await client.loadPlcArtifact(plc.instanceId, r.module);
    const prog = r.entry.programName;
    const forcar = async (entradas) => {
      for (const [k, v] of Object.entries(entradas)) await client.plcForce(plc.instanceId, `${prog}.${k}`, String(v));
    };
    // aquecimento: o primeiro ciclo do worker
    if (vetores.casos.length) await forcar(vetores.casos[0].entradas);
    await client.step(1e9);
    for (const caso of vetores.casos) {
      await forcar(caso.entradas);
      await client.step(Math.round((caso.segundos ?? 0.5) * 1e9));
      const lidos = {};
      for (const k of vetores.ler) {
        try { lidos[k] = numero(await client.plcGet(plc.instanceId, `${prog}.${k}`)); } catch { lidos[k] = null; }
      }
      saida.casos.push({ nome: caso.nome, lidos });
    }
    saida.ok = true;
  } catch (e) {
    saida.erros.push(e.message);
  } finally {
    await client.stop().catch(() => undefined);
    pm.kill();
  }
  console.log(JSON.stringify(saida));
})().catch((e) => { console.log(JSON.stringify({ ok: false, erros: [String(e && e.message || e)] })); process.exit(0); });
