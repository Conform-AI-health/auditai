# AuditIA — Regras Permanentes do Workspace (AGENTS.md)

Este arquivo define as restrições permanentes e inegociáveis para qualquer agente que opere no repositório **AuditIA**. Restrições clínicas e de segurança somente poderão ser alteradas mediante autorização expressa.

## 1. Domínio Clínico, Regulatório e Supervisão Humana (Imutáveis)
- **Supervisão Médica Indelegável:** O AuditIA é um sistema de apoio à decisão. É proibido implementar autorização ou negativa automática, substituir o julgamento médico ou remover etapas de aceite do termo (`CFM-2454-2026-v1`) e revisão humana.
- **Preservação da DUT 60:** Não alterar a lógica determinística, os 10 subitens da DUT 60, a separação entre **Eixo A** (conformidade regulatória expressa) e **Eixo B** (suficiência documental/clínica) nem os arquivos de runtime `mvp/backend/INSTRUCOES.md`, `mvp/backend/DUT60.txt` e `mvp/backend/criterios_dut.py`.
- **Preservação do SLA (RN ANS nº 623/2024):** Não alterar o cálculo determinístico de prazos em `mvp/backend/datas.py`. O único marco inicial válido do SLA (10 dias úteis para PAC) é `data_protocolo_operadora`. Na ausência dessa data, o status deve permanecer `PROTOCOLO_AUSENTE` (nunca substituir silenciosamente por data do SIGO ou de importação).
- **Módulo Gerencial Desabilitado:** Manter `/gerencia`, `/caso/gerencia` e `/pacote/<id>` desabilitados (`404 Not Found`) na Beta 0.2, preservando dados históricos no banco.

## 2. Segurança, CSP, Autenticação e Persistência (Imutáveis)
- **Preservar a CSP:** É estritamente proibido desativar, remover ou enfraquecer a política `Content-Security-Policy` em `mvp/backend/app.py` (`default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'`).
- **Zero Estilos Inline e Zero Fontes Remotas:** Como `style-src 'self'` bloqueia atributos `style="..."` inline e `@import` externos, todo estilo deve residir em classes CSS em `mvp/frontend/static/estilo.css` e toda fonte deve ser servida localmente (`'self'`).
- **Autenticação, Permissões e Isolamento:** Preservar integralmente a verificação JWT, proteção CSRF, rate-limit de login, isolamento multi-tenant (`tenant_id` obrigatório nas queries) e segregação entre perfis `auditor` e `admin`.
- **Credenciais e Senhas:** Proibido rotacionar, redefinir ou expor senhas de usuários existentes, alterar `AUDITIA_JWT_SECRET` ou exibir credenciais na interface pública.
- **Bancos de Dados e Modo de Execução:** Proibido alterar, sobrescrever, apagar ou migrar `mvp/auditia-governanca-demo.sqlite3` e `mvp/auditia-beta.sqlite3`, bem como alterar o modo de execução (`AUDITIA_BETA`, porta `5000` ou scripts de inicialização) sem autorização humana explícita.

## 3. Identidade Visual e Diretrizes da Interface (Aetherfield)
- **Fonte Visual:** Seguir estritamente os tokens validados em `DESIGN.md` (paleta Aetherfield: `#000000`, `#FFFFFF`, `#F6F8FB`, `#DBE0EC`, `#2683EB`, `#FFF546` e gradiente `--background-3`). A paleta legada (areia, terracota, bordô) é proibida.
- **Cabeçalho Público (`header.header-landing`):** Deve conter **somente o logotipo AuditIA**, sem links de navegação ou botões adicionais no cabeçalho.
- **Hero da Landing Page:** Os botões comerciais (`Solicitar demonstração` e `Acessar plataforma`) devem permanecer **centralizados no Hero**.
- **Proibido Inventar Métricas Comerciais:** Não criar nem exibir percentuais, estatísticas de ROI ou alegações quantitativas não comprovadas (ex.: proibido exibir `+45% produtividade médica` ou similares).

## 4. Rigor Técnico e Epistemológico
- **Fatos vs. Hipóteses:** Nunca classificar hipóteses, inferências ou entregas parciais como fatos confirmados. Toda afirmação técnica deve citar evidência verificável (arquivo, linha, output de comando ou status HTTP).
- **Trabalho Incremental e Aprovação:** Não executar commits, pushes, merges, deploys ou operações destrutivas sem solicitação explícita.

## 5. Mapa de Contexto Sob Demanda
- Identidade visual e componentes: `DESIGN.md`
- Estado atual, checkpoints e pendências: `PROJECT_STATE.md`
