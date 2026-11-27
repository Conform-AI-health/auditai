# AuditIA — Estado do Projeto (PROJECT_STATE.md)

## 1. Ambiente e Baseline
- **Branch ativa:** `feature/aetherfield-design-system`
- **Commit baseline:** `f4856b4`
- **Pitch / Prazo Alvo:** `01/12/2026`
- **Servidor local:** `http://127.0.0.1:5000` (`iniciar_auditia.cmd` / `iniciar_auditia.ps1`)
- **Interpretador:** `C:\Users\Mirella\AppData\Local\Programs\Python\Python312\python.exe`
- **Modo padrão:** `AUDITIA_BETA` desligado (`config.BETA = False`) → utiliza `mvp/auditia-governanca-demo.sqlite3`. Quando `AUDITIA_BETA=1`, utiliza `mvp/auditia-beta.sqlite3`.

## 2. Checkpoints Concluídos
- **Sprint 00 (Diagnóstico):** Identificadas as causas da divergência visual na porta 5000 (141 estilos inline bloqueados por `style-src 'self'`, `@import` do Google Fonts bloqueado por CSP, PNGs do logotipo com margens brancas excessivas e desalinhamento interno, sobreposição do visualizador documental sem estilos externos e loop de navegação entre `/login`, `/` e `/beta`).
- **Sprint 01 / Execução:**
  - Regras permanentes consolidadas em `AGENTS.md` e `DESIGN.md` alinhado às decisões obrigatórias.
  - Migração integral dos estilos inline (`style="..."`) para classes em `mvp/frontend/static/estilo.css` (100% compatível com `style-src 'self'`).
  - Fontes oficiais (`Source Serif 4`, `Radio Canada Big`, `Geist Mono`) servidas localmente em `/fonts/*`.
  - Logotipos oficiais (`logo_horizontal.png`, `logo_vertical.png`) recortados e alinhados com classes CSS dedicadas.
  - Visualizador documental (`/caso/<id>`) contido em grid responsivo e sem bloqueio de visualização.
  - Navegação corrigida entre `/`, `/landing`, `/login` e painel autenticado sem loop de cookie `role="login"` e sem link quebrado para `/beta` quando `config.BETA = False`.
  - Landing page institucional aprovada e commitada (`9c42cfa`).
- **Sprint 02 (Dashboard Médico Aprovado Visualmente pela Product Owner):**
  - Título padronizado para "Painel de auditoria médica" com área útil ampliada (margens laterais de 24 px).
  - 4 cards de KPIs dinâmicos ajustados com rótulos no topo (Geist Mono 13px) e números abaixo (Radio Canada Big 40px), mantendo 3 cards brancos (`#FFFFFF`) e "Revisão médica" em amarelo Aetherfield (`#FFF546`).
  - Seção de integração recolhível atualizada para "Integração com a operadora — SIGO/Oracle" com botão único "Importar solicitações" (conectores simulados MV e TASY preservados no backend para expansão futura).
  - Tabela reestruturada para conter exatamente 9 colunas na ordem e proporção aprovadas: Nº da guia (8%), Cód. beneficiário (10%), Procedimento (15%), Situação SLA (11%), Data limite (8%), Status da análise (13%), Pendência documental (12%), Médico responsável (11%), Ações (12%).
  - Espaçamentos horizontais compactados (especialmente entre Procedimento/SLA e Data limite/Status da análise), rolagem vertical interna adaptável à janela (`max-height: calc(100vh - 350px)`), cabeçalho fixo (`position: sticky; top: 0;`) e zero rolagem horizontal (validado em 1280x720, 1366x768, 1440x900 e 1920x1080).
  - Indicadores discretos de SLA e status da análise, com preservação dos dados das colunas retiradas (Entrada, Dias restantes, Revisão médica e Encaminhamento) em atributos e tooltips contextuais.
  - Ações com botão de acesso prioritário único (`Analisar`, `Continuar`, `Revisar` ou `Visualizar`) e menu recolhível de três pontos (`···`) posicionados lado a lado, integralmente visíveis sem sobreposição ou truncamento.
  - **Aprovação visual definitiva do dashboard médico pela Product Owner em 25/11/2026.**

## 3. Pendências Atuais
- Validação visual dos fluxos subsequentes (tela individual da guia `/caso/<id>` e fluxo conclusivo de parecer).
- Definição humana sobre unificação futura ou manutenção separada dos modos `AUDITIA_BETA=0` (`/` — `cases_page`) e `AUDITIA_BETA=1` (`/beta` — `fila.painel`).
