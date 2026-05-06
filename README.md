# 🎸 Transpositor de Cifras PDF

Ferramenta web para transpor cifras musicais em PDF para qualquer tom — **100% no browser, sem API, sem backend, sem custo**.

## ✨ Funcionalidades

- 📄 **Suporte a PDF com texto** — extração direta via PDF.js
- 🔍 **OCR automático** — PDFs escaneados, fotos e imagens via Tesseract.js
- 🎹 **24 tons disponíveis** — 12 maiores + 12 menores
- 🔧 **Correção manual do tom de origem** — caso a detecção automática erre
- 💾 **Exporta PDF formatado** — acordes + letra com fonte monoespaçada
- ⚡ **Transposição instantânea** — algoritmo puro em JavaScript (semitons)
- 🌐 **Funciona offline** — após carregamento inicial das libs CDN

## 🚀 Como usar

### Opção 1 — GitHub Pages (recomendado)

1. Fork este repositório
2. Vá em **Settings → Pages → Branch: main / root**
3. Acesse `https://seu-usuario.github.io/cifra-transposer/`

### Opção 2 — Local

Basta abrir o `index.html` direto no navegador (Chrome, Edge ou Firefox):

```bash
# Clone ou baixe o repositório
git clone https://github.com/seu-usuario/cifra-transposer.git
cd cifra-transposer

# Abra no navegador
open index.html          # macOS
start index.html         # Windows
xdg-open index.html      # Linux
```

> ⚠️ Para que o OCR funcione localmente (PDFs escaneados), abra via servidor HTTP:
> ```bash
> python3 -m http.server 8080
> # Acesse http://localhost:8080
> ```

## 🎵 Como funciona

### Transposição (puro JavaScript)

```
C → G  =  +7 semitons
Am → Dm =  +5 semitons
```

O algoritmo:
1. Detecta linhas de acordes (tokens que correspondem a padrões de acorde)
2. Calcula o intervalo em semitons entre o tom de origem e destino
3. Transpõe cada raiz de acorde preservando a qualidade (m, 7, maj7, sus4…) e o baixo em acordes com barra (C/E)
4. Decide por sustenidos (#) ou bemóis (b) conforme a convenção do tom destino

### Suporte a formatos de cifra

| Formato | Exemplo | Suportado |
|---------|---------|-----------|
| Linha de acordes | `Am  G  F  E7` | ✅ |
| Acorde com qualidade | `Cmaj7 Dm7 G9` | ✅ |
| Acorde com barra | `C/E Am/G` | ✅ |
| Acordes entre colchetes | `[Am]palavra` | ✅ |
| Tablatura (notas) | `e|--0--2--` | ➖ ignorada |

### OCR (Tesseract.js)

Para PDFs escaneados ou fotos:
- Cada página é renderizada em canvas 2x via PDF.js
- As imagens são processadas pelo Tesseract.js (WASM, roda no browser)
- Idiomas: Português + Inglês
- Após OCR, a detecção de tom e transposição seguem o mesmo fluxo

## 📦 Dependências (todas via CDN)

| Biblioteca | Versão | Uso |
|-----------|--------|-----|
| [PDF.js](https://mozilla.github.io/pdf.js/) | 3.11 | Extração de texto e render de páginas |
| [Tesseract.js](https://tesseract.projectnaptha.com/) | 5.x | OCR para PDFs escaneados (lazy load) |
| [jsPDF](https://parall.ax/products/jspdf) | 2.5 | Geração do PDF transposto |

> Tesseract.js (~30MB de modelos) é carregado **somente quando necessário** (PDF sem texto).

## 🗂 Estrutura

```
cifra-transposer/
├── index.html   ← aplicação completa (single file)
└── README.md
```

## 📝 Licença

MIT — use, modifique e distribua à vontade.
