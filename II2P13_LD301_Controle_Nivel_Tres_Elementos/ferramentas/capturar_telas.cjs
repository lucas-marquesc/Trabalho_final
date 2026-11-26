// Captura de telas da prática II2P13 no LasecSimul REAL (extensão instalada no VS Code).
//
// Abre uma cópia do projeto num VS Code de teste isolado (perfil e extensões temporários), carrega a
// extensão LasecSimul instalada como "extensão em desenvolvimento", abre o .lsproj, roda a simulação
// e grava as capturas. Os arquivos originais da prática não são alterados.
//
// Uso (Node 18+, a partir da pasta da prática):
//   node ferramentas/capturar_telas.cjs <roteiro.json>
// O roteiro diz qual projeto abrir e a sequência de ações/capturas (ver ferramentas/roteiros/).
//
// Dependências reaproveitadas do repositório do LasecSimul (C:\SourceCode\LasecSimul\extension):
// Playwright (CDP) e o VS Code de teste baixado pelo @vscode/test-electron.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const LASEC = process.env.LASECSIMUL_REPO || "C:/SourceCode/LasecSimul";
const { chromium } = require(path.join(LASEC, "extension", "node_modules", "@playwright", "test"));
const VSCODE = process.env.LASECSIMUL_VSCODE ||
  path.join(LASEC, "extension", ".vscode-test", "vscode-win32-x64-archive-1.128.0", "Code.exe");
const EXTENSAO = process.env.LASECSIMUL_EXTENSAO ||
  path.join(os.homedir(), ".vscode", "extensions", "josuemoraisgh.lasecsimul-0.0.93");
const PRATICA = path.resolve(__dirname, "..");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function copiarPratica() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), "ii2p13-captura-"));
  for (const nome of fs.readdirSync(PRATICA)) {
    if (nome.endsWith(".lsproj")) fs.copyFileSync(path.join(PRATICA, nome), path.join(destino, nome));
  }
  fs.mkdirSync(path.join(destino, "clp"));
  for (const nome of fs.readdirSync(path.join(PRATICA, "clp"))) {
    fs.copyFileSync(path.join(PRATICA, "clp", nome), path.join(destino, "clp", nome));
  }
  return destino;
}

async function iniciar(pasta, { largura = 1900, altura = 1060, tema = "Default Light Modern" } = {}) {
  const porta = 9400 + Math.floor(Math.random() * 400);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "ii2p13-user-"));
  const extDir = fs.mkdtempSync(path.join(os.tmpdir(), "ii2p13-ext-"));
  fs.mkdirSync(path.join(userData, "User"), { recursive: true });
  fs.writeFileSync(path.join(userData, "User", "settings.json"), JSON.stringify({
    "workbench.colorTheme": tema, "window.zoomLevel": 0, "workbench.startupEditor": "none",
    "lasecsimul.network.mode": "isolated", "security.workspace.trust.enabled": false,
  }));
  const env = { ...process.env, LASECSIMUL_E2E: "1" };
  delete env.ELECTRON_RUN_AS_NODE;
  let saida = "";
  const filho = spawn(VSCODE, [
    `--remote-debugging-port=${porta}`, `--user-data-dir=${userData}`, `--extensions-dir=${extDir}`,
    `--extensionDevelopmentPath=${EXTENSAO}`, "--disable-workspace-trust", "--disable-updates", "--skip-welcome",
    "--force-device-scale-factor=1", "--disable-gpu", "--new-window", pasta,
  ], { env, stdio: ["ignore", "pipe", "pipe"] });
  const guardar = (b) => { saida = (saida + b.toString()).slice(-30000); };
  filho.stdout.on("data", guardar);
  filho.stderr.on("data", guardar);
  let browser;
  for (let i = 0; i < 160 && !browser; i += 1) {
    try { browser = await chromium.connectOverCDP(`http://127.0.0.1:${porta}`); } catch { await sleep(250); }
  }
  if (!browser) throw new Error("VS Code de teste não iniciou\n" + saida);
  let wb;
  for (let i = 0; i < 200 && !wb; i += 1) {
    wb = browser.contexts().flatMap((c) => c.pages()).find((p) => p.url().includes("workbench"));
    if (!wb) await sleep(250);
  }
  if (!wb) throw new Error("Workbench não abriu");
  await wb.locator(".monaco-workbench").waitFor({ state: "visible", timeout: 60000 });
  await wb.setViewportSize({ width: largura, height: altura });
  const fechar = async () => { await browser.close().catch(() => {}); filho.kill(); };
  return { wb, browser, fechar, log: () => saida };
}

async function comando(wb, titulo) {
  await wb.keyboard.press("Control+Shift+P");
  const entrada = wb.locator(".quick-input-widget input").first();
  await entrada.waitFor({ state: "visible", timeout: 15000 });
  await entrada.fill(">" + titulo);
  await sleep(900);
  await wb.keyboard.press("Enter");
}

async function abrirArquivo(wb, nome) {
  await wb.keyboard.press("Control+P");
  const entrada = wb.locator(".quick-input-widget input").first();
  await entrada.waitFor({ state: "visible", timeout: 15000 });
  await entrada.fill(nome);
  const linha = wb.locator(".quick-input-list .monaco-list-row").first();
  await linha.waitFor({ state: "visible", timeout: 15000 });
  await sleep(800);
  await linha.click();
  await sleep(1000);
  if (await entrada.isVisible().catch(() => false)) await wb.keyboard.press("Enter");
}

async function quadroEsquematico(wb, idComponente, tentativas = 240) {
  for (let i = 0; i < tentativas; i += 1) {
    for (const quadro of wb.frames()) {
      if (quadro === wb.mainFrame()) continue;
      const alvo = quadro.locator(`.component[data-component-id="${idComponente}"]`).first();
      if (await alvo.count().catch(() => 0)) return quadro;
    }
    await sleep(250);
  }
  return undefined;
}

async function executar(roteiro) {
  const pasta = roteiro.pasta || copiarPratica();
  console.log("pasta de trabalho:", pasta);
  const saidaDir = path.resolve(PRATICA, roteiro.saida || "assets");
  fs.mkdirSync(saidaDir, { recursive: true });
  const sessao = await iniciar(pasta, roteiro.janela || {});
  const { wb } = sessao;
  const ctx = { wb, quadro: undefined, pasta };
  try {
    await sleep(5000);
    for (const passo of roteiro.passos) {
      const [acao, ...args] = passo;
      console.log("->", acao, args.join(" "));
      if (acao === "vista") {
        // grava a vista inicial (pan/zoom) na CÓPIA do projeto antes de abri-la: arquivo, x, y, zoom
        const [arquivo, x, y, zoom] = args;
        const alvo = path.join(pasta, arquivo);
        const doc = JSON.parse(fs.readFileSync(alvo, "utf8"));
        doc.visual = { ...(doc.visual || {}), viewport: { x: +x, y: +y, zoom: +zoom } };
        fs.writeFileSync(alvo, JSON.stringify(doc, null, 2));
      } else if (acao === "abrir") {
        await abrirArquivo(wb, args[0]);
        ctx.quadro = await quadroEsquematico(wb, args[1] || "ii2p13-planta");
        if (!ctx.quadro) throw new Error("esquemático não abriu");
        await sleep(3000);
      } else if (acao === "abrirPlc") {
        // abre um .lsplc no editor OpenPLC do LasecSimul e espera o quadro ficar pronto
        await abrirArquivo(wb, args[0]);
        ctx.plc = undefined;
        for (let i = 0; i < 480 && !ctx.plc; i += 1) {
          for (const quadro of wb.frames()) {
            if (quadro === wb.mainFrame()) continue;
            if (await quadro.evaluate(() => document.body?.dataset.lasecOpenplc === "ready").catch(() => false)) ctx.plc = quadro;
          }
          if (!ctx.plc) await sleep(250);
        }
        if (!ctx.plc) throw new Error("editor OpenPLC não abriu");
        await sleep(2500);
      } else if (acao === "plcDuplo") {
        await ctx.plc.getByText(args[0], { exact: true }).first().dblclick();
        await sleep(Number(args[1] || 2000));
      } else if (acao === "plcClique") {
        await ctx.plc.getByText(args[0], { exact: true }).first().click();
        await sleep(Number(args[1] || 1000));
      } else if (acao === "plcBotao") {
        await ctx.plc.locator(`button[aria-label="${args[0]}"]`).first().click();
        await sleep(Number(args[1] || 2000));
      } else if (acao === "plcJs") {
        const r = await ctx.plc.evaluate(args[0]).catch((e) => `ERRO ${e.message}`);
        console.log("   =", typeof r === "string" ? r : JSON.stringify(r));
      } else if (acao === "teclas") {
        await wb.keyboard.press(args[0]);
        await sleep(600);
      } else if (acao === "comando") {
        await comando(wb, args[0]);
        await sleep(Number(args[1] || 1500));
      } else if (acao === "esperar") {
        await sleep(Number(args[0]));
      } else if (acao === "captura") {
        const arquivo = path.join(saidaDir, args[0]);
        await wb.screenshot({ path: arquivo });
        console.log("   ", arquivo);
      } else if (acao === "recorte") {
        // recorte em coordenadas da janela: x, y, largura, altura
        const [arquivo, x, y, w, h] = args;
        await wb.screenshot({ path: path.join(saidaDir, arquivo), clip: { x: +x, y: +y, width: +w, height: +h } });
      } else if (acao === "js") {
        // avalia uma expressão dentro do quadro do esquemático e imprime o resultado
        const r = await ctx.quadro.evaluate(args[0]).catch((e) => `ERRO ${e.message}`);
        console.log("   =", typeof r === "string" ? r : JSON.stringify(r));
      } else if (acao === "jsWorkbench") {
        const r = await wb.evaluate(args[0]).catch((e) => `ERRO ${e.message}`);
        console.log("   =", typeof r === "string" ? r : JSON.stringify(r));
      } else if (acao === "botao") {
        // botão da barra do esquemático pelo título (ex.: "Run simulation", "Zoom to fit all")
        const botao = ctx.quadro.locator(`button[title="${args[0]}"]`).first();
        if (await botao.isVisible().catch(() => false)) {
          await botao.click({ timeout: 5000 }).catch((e) => console.log("   (botão não clicado:", e.message.split("\n")[0], ")"));
        } else {
          console.log("   (botão ausente:", args[0], ")");
        }
        await sleep(Number(args[1] || 800));
      } else if (acao === "zoom") {
        // zoom do esquemático com a roda do mouse sobre um ponto da janela: x, y, passos (+ aproxima)
        const [x, y, passos] = args.map(Number);
        await wb.mouse.move(x, y);
        for (let i = 0; i < Math.abs(passos); i += 1) { await wb.mouse.wheel(0, passos > 0 ? -120 : 120); await sleep(120); }
        await sleep(500);
      } else if (acao === "texto") {
        // clica no primeiro elemento do esquemático (ou painel Properties) com o texto dado
        await ctx.quadro.getByText(args[0], { exact: false }).first().click();
        await sleep(Number(args[1] || 1500));
      } else if (acao === "componente") {
        // seleciona um componente do esquemático pelo id (clique no centro da caixa)
        const alvo = ctx.quadro.locator(`.component[data-component-id="${args[0]}"]`).first();
        const caixa = await alvo.boundingBox();
        if (!caixa) throw new Error(`componente ${args[0]} fora da tela`);
        const fx = args[1] !== undefined ? Number(args[1]) : 0.5;
        const fy = args[2] !== undefined ? Number(args[2]) : 0.5;
        await wb.mouse.click(caixa.x + caixa.width * fx, caixa.y + caixa.height * fy);
        await sleep(1500);
      } else if (acao === "overlay") {
        // controle operável do sinótico: índice entre os overlays interativos e fração da largura
        // (0..1) onde clicar -- num slider, a fração vira o valor entre actionMin e actionMax
        const [indice, fracao] = args.map(Number);
        const alvo = ctx.quadro.locator(".component--board-overlay--interactive").nth(indice);
        const caixa = await alvo.boundingBox();
        if (!caixa) throw new Error(`overlay ${indice} sem caixa`);
        await wb.mouse.click(caixa.x + caixa.width * (Number.isFinite(fracao) ? fracao : 0.5), caixa.y + caixa.height / 2);
        await sleep(600);
      } else if (acao === "clicar") {
        await wb.mouse.click(+args[0], +args[1]);
        await sleep(400);
      } else if (acao === "arrastar") {
        const [x1, y1, x2, y2] = args.map(Number);
        await wb.mouse.move(x1, y1);
        await wb.mouse.down();
        await wb.mouse.move(x2, y2, { steps: 12 });
        await wb.mouse.up();
        await sleep(400);
      } else {
        throw new Error("ação desconhecida: " + acao);
      }
    }
  } catch (erro) {
    console.error("FALHA:", erro.message);
    await wb.screenshot({ path: path.join(saidaDir, "_falha.png") }).catch(() => {});
    console.error(sessao.log().slice(-4000));
    process.exitCode = 1;
  } finally {
    if (!roteiro.manterAberto) await sessao.fechar();
  }
}

const arquivo = process.argv[2];
if (!arquivo) {
  console.error("uso: node ferramentas/capturar_telas.cjs <roteiro.json>");
  process.exit(2);
}
executar(JSON.parse(fs.readFileSync(arquivo, "utf8"))).catch((e) => { console.error(e); process.exitCode = 1; });
