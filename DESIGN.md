# AuditIA — Diretrizes e Especificação do Design System (Aetherfield)

Este documento estabelece a **fonte única de verdade** da identidade visual do **AuditIA**, adotando com fidelidade visual máxima o design system do template **Aetherfield**.

A antiga paleta (areia, terracota, bordô e roxo) está **completamente descontinuada e revogada**.

---

## 1. Princípios de Design

1. **Clareza Editorial & Minimalismo de Alta Precisão:** Interfaces limpas, tipografia com contraste hierárquico refinado e linhas limpas.
2. **Fidelidade aos Tokens Oficiais:** Nenhuma cor, raio de curvatura ou tamanho de fonte deve ser inventado fora dos tokens validados.
3. **Semântica e Rigor Clínico:** Alertas e semáforos regulatórios (DUT 60, SLA, evidências documentais) utilizam a sobriedade e o refinamento do design system, mantendo distinção visual imediata e acessibilidade WCAG AAA/AA.
4. **Microinterações Sutis:** Transições suaves (200ms–300ms `ease-in-out`), elevação sob hover e foco visível acessível.

---

## 2. Paleta de Cores e Design Tokens

### 2.1 Cores Principais (Aetherfield Official)

| Token | Valor HEX | Uso no AuditIA |
|---|---|---|
| `--color-headline` | `#000000` | Títulos principais (H1, H2, H3), textos de alto impacto |
| `--color-paragraph-1` | `#000000` | Texto primário do corpo, dados do caso, valores de tabelas |
| `--color-paragraph-2` | `#6C6C6C` | Texto secundário, descrições, metadados, subtítulos |
| `--color-paragraph-3` | `#66640F` | Texto terciário (usado com fundo amarelo em badges e tags) |
| `--color-sticker` / `--color-link` | `#2683EB` | Azul de destaque, links, foco ativo, acentos da marca (`Audit`**IA**) |
| `--color-button-text` | `#FFFFFF` | Texto em botões principais escuros |
| `--color-background-1` | `#FFFFFF` | Superfície principal de cartões, formulários e painéis |
| `--color-background-2` | `#F6F8FB` | Fundo secundário, canvas de tabelas, áreas alternadas |
| `--color-background-4` (Yellow) | `#FFF546` | Badges de alerta de SLA, tags de governança, destaque |
| `--color-background-5` (Dark) | `#000000` | Botões primários, cabeçalhos de alto contraste, rodapé |
| `--color-divider` | `#DBE0EC` | Linhas divisórias, bordas de cards, bordas de tabelas |
| `--color-border-dark` | `#000000` | Bordas de cards de destaque (1px ou 2px solid #000) |

### 2.2 Gradiente Hero (Aetherfield Signature Gradient)
- **Token:** `--background-3`
- **Valores:** Linear de `top` para `bottom`:
  - Início (0%): `#A8D3FF` (`rgba(168, 211, 255, 1)`)
  - Meio (50%): `#D3E3EF` (`rgba(211, 227, 239, 1)`)
  - Fim (100%): `#FFF4DF` (`rgba(255, 244, 223, 1)`)
- **Aplicação:** Fundo da seção Hero (Landing Page, cabeçalhos de destaque e boas-vindas da fila médica).

### 2.3 Cores de Status e Regulação Clínica (Harmonizadas)

| Status | Fundo | Borda | Texto | Aplicação Regulatória |
|---|---|---|---|---|
| **Conforme / Atendido** | `#ECFDF3` | `1px solid #16803C` | `#14532D` | DUT 60 Atendida, SLA no prazo, Parecer favorável |
| **Alerta / Em Risco** | `#FFF546` | `1px solid #E6DC30` | `#66640F` | SLA em alerta (≤ 3 dias), Pendência documental |
| **Vencido / Não Atendido** | `#FFF0EF` | `1px solid #B42318` | `#7A271A` | SLA estourado, DUT não atendida, Indeferimento |
| **Informativo / Neutro** | `#F6F8FB` | `1px solid #DBE0EC` | `#2683EB` | Triagem TUSS × Rol, Minuta preliminar, Documento conferido |

---

## 3. Tipografia Oficial

São utilizadas rigorosamente as três famílias tipográficas identificadas no template original:

1. **Source Serif Pro (ou Source Serif 4):**
   - Headings editoriais (`header-1`), parágrafos literários (`paragraph-2`, `article-paragraph`), citações e pareceres.
2. **Radio Canada Big:**
   - Headings modernos (`header-2`, `header-3`, `header-4`), corpo de texto padrão (`paragraph-1`), links de navegação (`nav-link`) e rótulos de formulário.
3. **Geist Mono:**
   - Botões (`button-text`), legendas (`caption`), códigos TUSS, números de guias, hashes SHA-256, datas e badges de status.

### 3.1 Escala Tipográfica Responsiva

| Utility Class | Família | Peso | Tamanho Mobile | Tamanho Tablet (800px) | Tamanho Desktop (1280px) | Line Height | Letter Spacing |
|---|---|---|---|---|---|---|---|
| `header-1` | Source Serif Pro | 400 | 36px | 64px | 80px | 100% | -4% |
| `header-2` | Radio Canada Big | 400 | 36px | 64px | 80px | 100% | -2% (m) / -5% (d) |
| `header-3` | Radio Canada Big | 500 | 32px | 48px | 56px | 100% | -3% |
| `header-4` | Radio Canada Big | 500 | 24px | 32px | 40px | 100% | -3% |
| `paragraph-1` | Radio Canada Big | 400 | 18px | 20px | 20px | 100% | -2% |
| `paragraph-1-medium` | Radio Canada Big | 500 | 18px | 20px | 20px | 100% | -2% |
| `paragraph-2` | Source Serif Pro | 400 | 18px | 20px | 20px | 120% | -3% (m) / -4% (d) |
| `article-paragraph` | Source Serif Pro | 400 | 18px | 20px | 20px | 140% | -3% (m) / -4% (d) |
| `nav-link` | Radio Canada Big | 500 | 16px | 16px | 16px | 120% | 0% |
| `button-text` | Geist Mono | 500 | 14px | 14px | 14px | 100% | 0% |
| `caption` | Geist Mono | 400 | 14px | 14px | 14px | 100% | 0% |

---

## 4. Estrutura, Espaçamento e Geometria

### 4.1 Breakpoints
- **Mobile:** `< 800px`
- **Tablet:** `800px`
- **Desktop:** `1280px`

### 4.2 Containers & Layout
- Largura máxima de conteúdo padrão: `1240px` (desktop), centralizado com padding lateral `20px` a `40px`.
- Hero Section: Largura total (100%), preenchido com `--background-3`.

### 4.3 Raios de Curvatura (Border Radius)
- **Cards grandes:** `20px` a `24px`
- **Cards secundários e modais:** `16px` a `20px`
- **Inputs, botões e caixas de texto:** `10px` a `12px`
- **Pills e Badges:** `9999px` (circular / pill shape)

### 4.4 Sombras e Elevação
- **Sombra sutil (Cards padrão):** `0 1px 3px rgba(0, 0, 0, 0.05), 0 8px 24px rgba(0, 0, 0, 0.03)`
- **Sombra hover (Cards interativos):** `0 4px 12px rgba(0, 0, 0, 0.08), 0 16px 36px rgba(0, 0, 0, 0.06)`
- **Sombra modal/dropdown:** `0 12px 48px rgba(0, 0, 0, 0.14)`

---

## 5. Componentes Principais

### 5.1 Cabeçalho e Navegação (Header & Navbar)
- **Posicionamento:** `sticky top: 0`, `z-index: 1040`.
- **Efeito visual:** `backdrop-filter: blur(20px) saturate(180%)`, fundo `rgba(255, 255, 255, 0.72)` (ou `0.50` na Landing Page) com transição suave.
- **Divisor inferior:** `1px solid rgba(219, 224, 236, 0.65)`.
- **Logotipo AuditIA:**
  - Componente oficial com imagem estática (`logo_horizontal.png` no header com `36px` de altura e no rodapé com `28px`; `logo_vertical.png` no login com `76px` de altura), dimensionado exclusivamente via classes CSS (`.logo-auditia`, `.logo-horizontal`, `.logo-vertical`) em conformidade com a CSP (`style-src 'self'`).
- **Cabeçalho Público (`header.header-landing`):** Contém **exclusivamente o logotipo AuditIA**, sem links ou botões adicionais.
- **Badge de Operadora/Perfil:** Fundo `#FFF546`, texto `#66640F`, fonte Geist Mono 12px, border-radius `var(--radius-full)`.
- **Links (área autenticada):** Fonte Radio Canada Big 15px (medium 500), cor `#000000`, hover `opacity: 0.75`.

### 5.2 Botões
- **Primário (Aetherfield Dark Button):**
  - Fundo `#000000`, texto `#FFFFFF`.
  - Fonte Geist Mono 14px (medium 500).
  - Ícone de quadrado sólido 4×4px ou seta Aetherfield.
  - Padding `14px 22px`.
  - Raio `12px` ou `9999px`.
  - Hover: texto `#CCCCCC`, sombra `0 4px 14px rgba(0, 0, 0, 0.18)`, leve escala ou translação.
- **Secundário (Outline/Light):**
  - Fundo `#FFFFFF`, borda `1px solid #DBE0EC`, texto `#000000`.
  - Hover: fundo `#F6F8FB`.
- **Link com Seta:**
  - Texto `#000000`, fonte Radio Canada Big 16px, com ícone de seta SVG (`arrow.svg`) que translada 3px à direita no hover.

### 5.3 Cartões e Painéis (Cards)
- Fundo `#FFFFFF`, borda `1px solid #DBE0EC`, raio `20px` ou `24px`.
- Padding interno generoso: `28px` a `36px`.
- Header do card com etiqueta em Geist Mono (`caption`) e título em Radio Canada Big (`header-3` ou `header-4`).

### 5.4 Tabelas de Auditoria (Fila de Casos e Trilha de Governança)
- Fundo do container `#FFFFFF`, borda externa `1px solid #DBE0EC`, raio `16px`.
- Cabeçalhos de coluna: Geist Mono 13px, maiúsculas ou pontuação discreta, fundo `#F6F8FB`, borda inferior `1px solid #DBE0EC`, texto `#6C6C6C`.
- Linhas da tabela: padding vertical `16px`, borda inferior `1px solid #DBE0EC`, hover em `#F6F8FB`.
- Dados técnicos (código TUSS, guia, SLA): Geist Mono.

### 5.5 Formulários e Entradas
- Rótulo (`label`): Radio Canada Big 500, cor `#000000`, margem inferior `8px`.
- Campo (`input`, `select`, `textarea`):
  - Fundo `#FFFFFF`, borda `1px solid #DBE0EC`, raio `10px`, padding `12px 16px`.
  - Texto `#000000`, placeholder `#6C6C6C`.
  - Foco: borda `#2683EB`, anel de foco `0 0 0 3px rgba(38, 131, 235, 0.25)`, sem outline bruto.
- Textarea para minutas: fonte Radio Canada Big / Source Serif Pro para texto corrido confortável de leitura.

---

## 6. Histórico de Versões e Transição

| Versão | Data | Descrição da Mudança |
|---|---|---|
| **Beta 0.1** | 2026-11-22 | Paleta legado (areia, terracota, bordô). **[REVOGADA]** |
| **Beta 0.2 — Aetherfield** | 2026-11-23 | Refatoração visual pixel-perfect integral. Adoção da paleta preto/branco/azul/amarelo, tipografia Source Serif Pro, Radio Canada Big e Geist Mono, gradiente #A8D3FF a #FFF4DF, divisores #DBE0EC e geometrias Aetherfield. |
| **Beta 0.2 — UX/UI V4.0** | 2026-11-24 | Implementação definitiva UX/UI V4.0: Landing Page comercial em 9 seções, Login independente, Dashboard Médico com 4 KPIs e tabela sem quebra vertical, Tela de Análise em grid de 2 colunas, Painel Administrativo modernizado, ativos estáticos oficiais e 10 screenshots de homologação responsiva. |

---

## 7. Implementação UX/UI V4.0 — Especificação Arquitetural de Telas

### 7.1 Inventário de Ativos Oficiais (`mvp/frontend/static/img/` e `mvp/frontend/static/fonts/`)
- `logo_horizontal.png`: Logotipo horizontal com símbolo neural circular e tipografia oficial AuditIA alinhados e recortados sem margens excedentes (altura via classe CSS: `36px` no header, `28px` no rodapé).
- `logo_vertical.png`: Logotipo vertical centralizado com símbolo neural sobre a tipografia (altura via classe CSS: `76px` na tela de login independente).
- `logo_symbol.png`: Símbolo neural recortado para ícones e favicon.
- `logo_text.png`: Tipografia oficial "AuditIA" recortada.
- `favicon.png` e `favicon.ico`: Favicons oficiais servidos diretamente em `/favicon.ico` e `/img/favicon.png`.
- `imagem_mulher.png`: Imagem oficial da seção de Eficiência Operacional com enquadramento focado no sujeito e bordas arredondadas (`var(--radius-2xl)`).
- Fontes licenciadas locais (`/fonts/*.woff2`): `Source Serif 4`, `Radio Canada Big` e `Geist Mono` carregadas via `@font-face` local (`'self'`), sem `@import` externo.

### 7.2 Landing Page Pública (`/`, `/landing`, `/inicio`)
Arquitetura 100% institucional e comercial sem credenciais públicas, dados operacionais, cards fictícios ou métricas inventadas:
1. **Header Glassmorphism (`header.header-landing`):** Translucidez com `backdrop-filter: blur(20px)`, contendo **exclusivamente o logotipo AuditIA** à esquerda.
2. **Hero Full-bleed:** Altura ampliada e espaços negativos generosos conforme Aetherfield (`min-height: 620px`, `padding: 168px 24px 152px`), headline editorial em `Source Serif 4`, subtítulo em `Radio Canada Big` e **somente o botão `Acessar plataforma` centralizado no Hero**.
3. **Seção de Eficiência Operacional:** Grid assimétrico com `imagem_mulher.png` à esquerda (sobreposta por banner horizontal em glassmorphism no canto inferior esquerdo, sem cobrir o rosto, contendo exclusivamente o logotipo oficial AuditIA em destaque) e 4 blocos objetivos à direita sem textos complementares (`001 — Organizar: Centralize informações clínicas e regulatórias.`, `002 — Analisar: Apoie decisões com mais consistência.`, `003 — Fundamentar: Transforme evidências em decisões rastreáveis.`, `004 — Ganhar eficiência: Reduza retrabalho e valorize o tempo médico.`).
4. **4 Cards de Benefícios:** Grid 4 colunas com microinterações, bordas sutis e tipografia precisa.
5. **Seção Geométrica:** "Construído para decisões melhores", contendo 3 cards com ilustrações geométricas em SVG.
6. **Governança & Rigor:** Supervisão médica humana indelegável e trilha local de auditoria, sem alegações de homologação ou desempenho não comprovadas.
7. **Interoperabilidade:** Identificação explícita de SIGO, MV e TASY como conectores simulados em ambiente demonstrativo com dados sintéticos.
8. **CTA Final:** Bloco de chamada comercial institucional em alto contraste (`#000000`) mantendo o botão `"Solicitar demonstração"` exclusivamente no final da página, desabilitado (`disabled`) e com indicação discreta `"Em breve"`.
9. **Rodapé Institucional:** Referências normativas, copyright e logotipo oficial.

### 7.3 Login Independente (`/login`, `/entrar`)
Página limpa e centralizada, sem credenciais expostas no HTML, com inputs neutros, logotipo vertical AuditIA e link funcional de retorno à página inicial (`/`).

### 7.4 Dashboard Médico Autenticado (`/` ou `/beta`)
- **Cabeçalho:** `Painel de auditoria médica` (em `/beta`) ou `Casos da Operadora` (em `/`) e subtítulo descritivo.
- **4 Cards de KPI:**
  - `Solicitações`: Fundo branco (`#FFFFFF`).
  - `Em análise`: Fundo branco (`#FFFFFF`).
  - `Revisão médica`: Fundo amarelo Aetherfield (`#FFF546`), texto `#000000`.
  - `Concluídas`: Fundo branco (`#FFFFFF`).
- **Tabela da Fila de Auditoria:**
  - Container `.tablewrap` com rolagem horizontal suave (`overflow-x: auto`).
  - Cabeçalhos em `Geist Mono` 12px uppercase (`white-space: nowrap`), sem quebra caractere por caractere.
  - Badges semânticos de SLA e documentação com cantos arredondados (`var(--radius-full)`).

### 7.5 Tela de Análise Médica (`/caso/<id>`)
Organização responsiva em grid de 2 colunas (`.case-grid-layout`), 100% estilizada via classes CSS externas compatíveis com `style-src 'self'`:
- **Coluna Esquerda (`.case-col-left`):**
  - Guia e origem (dados do caso, procedimento, código TUSS).
  - Documentos vinculados (visualizador documental contido sem sobreposição, transcrição textual fiel lado a lado em `.doc-compare-grid` e formulários retráteis de conferência médica e versão).
  - Semáforo de pendência documental fundamental.
  - Vínculo clínico-documental e evidências estruturadas com rastreabilidade.
- **Coluna Direita (`.case-col-right`):**
  - Triagem TUSS × Rol e avaliação fora do Rol.
  - Minutas Regulatórias AuditIA (Aprovação, Edição e Descarte pelo auditor).
  - Apoio decisório (DUT 60, checklist, critérios determinísticos).
  - Histórico preservado de execuções e formulário de revisão médica.

### 7.6 Painel Administrativo (`/` para perfil admin)
- Título: `Painel administrativo`.
- Subtítulo: `Gestão operacional, acessos e governança.`.
- 4 Cards de KPI administrativos (Usuários ativos, Auditores, Casos cadastrados, Execuções de IA).
- Grid modular com os 8 módulos de gestão da operadora.
