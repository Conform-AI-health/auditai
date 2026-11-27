# AuditIA — Especificação consolidada do dashboard médico auditor

Status: requisitos aprovados pela PO; implementação e validação pendentes. Revisão de entrega em arquivo para evitar truncamento no chat. Escopo: MVP sintético PET-CT oncológico/DUT 60.

## 0. Ambiente, contexto e execução
- Workspace Windows: `C:\Users\Mirella\Desktop\PROJETOS\AuditIA`; branch `feature/aetherfield-design-system`; checkpoint confirmado `7801fca`; working tree limpo no diagnóstico; servidor porta 5000 desligado. Banco `mvp/auditia-governanca-demo.sqlite3`, modo padrão, sem ativar beta. Verificar novamente antes de alterar.
- Não realizar push, merge, deploy, troca de ambiente/banco ou rotação de credenciais. Dados exclusivamente sintéticos; não commitar segredos, credenciais ou bancos locais.
- Ler AGENTS.md, DESIGN.md, PROJECT_STATE.md. Inspecionar código, rotas, serviços, esquema, autenticação, CSS e testes por buscas direcionadas. Reutilizar estruturas existentes; não reconstruir, duplicar regras ou introduzir dependências desnecessárias. Preservar telas e funcionalidades aprovadas.
- Persistir esta especificação completa em `docs/requirements/DASHBOARD.md` ou equivalente existente, sem duplicação; criar `docs/implementation/DASHBOARD_CHECKLIST.md` ou equivalente com ID, estado (pendente/em implementação/implementado/testado/bloqueado), arquivos, evidências, testes, resultados e pendências. Usar referências cruzadas. Estas regras prevalecem sobre definições anteriores conflitantes exclusivamente para o dashboard; conflitos relevantes devem ser registrados, não resolvidos silenciosamente.
- Trabalhar por fases: 0 persistência, diagnóstico e baseline; 1 integração/identidade; 2 segurança/fluxo; 3 funcionalidades do dashboard; 4 visual; 5 validação/documentação. Ao fim de cada fase executar testes pertinentes e registrar em checklist e PROJECT_STATE.md: etapa, próxima tarefa, decisões, arquivos, Git, testes, riscos e bloqueios. Persistir antes de interrupções/compactações; na retomada ler estado e verificar alterações locais, retomando primeira tarefa pendente, sem repetir trabalho validado.
- Economizar contexto: não carregar todo repositório, dependências, PDFs, bancos ou DUTs sem necessidade; ler somente trechos relevantes; resumir saídas e não repetir especificação no chat. Documentação versionada é fonte de verdade. Não presumir acesso ilimitado ao contexto; não pedir novamente informações já registradas.
- Limites: não desenvolver novas telas de análise individual, discussão com gerência ou administração; somente ajustes técnicos indispensáveis preservando interfaces existentes. Não ampliar DUT, não executar decisões autônomas. Registrar bloqueios sem ocultá-los. Não alterar requisitos sem autorização.

## REQ-01 — Fila e autenticação
Login individual, fila compartilhada Aurora Saúde, médicos autorizados podem assumir guias disponíveis, todos os autorizados da mesma operadora podem visualizar, isolamento entre operadoras, RBAC e identificação pelo ID autenticado no backend, produtividade individual. Não confiar apenas no frontend.

## REQ-02/03 — Identificação e divergências
- Triagem por código original, tabela de origem/versão (quando disponíveis), descrição e pedido médico original; variantes PET-CT, PET CT, PET/CT, PET-TC, PET Scan, tomografia por emissão de pósitrons; contemplar pedidos apenas por texto, códigos AMB/TUSS/internos. Correlacionar apenas equivalências validadas TUSS/Rol/DUT; sem inventar mapeamentos. Semântica sugere candidatos, não confirma equivalência. Não presumir que todo PET-CT pertence à DUT 60. Separar identificação, terminologia e motor clínico-regulatório.
- Preservar código/descrição/tabela originais, proveniência e evidência. Dados mínimos pertinentes: identificador pseudonimizado do beneficiário, sexo, idade, guia, protocolo original, data de entrada na operadora, procedimento, pedido/SADT, indicação/diagnóstico, laudos de imagem, exames laboratoriais pertinentes (ex. CEA), biópsia/anatomopatológico quando disponíveis ou exigidos pelo critério, demais documentos pertinentes. Não replicar informações irrelevantes ou transmitir dados identificáveis desnecessariamente para serviços externos.
- Divergências: sinalizar e mostrar evidências para conferência do auditor (guia, histórico hospitalar externo, contato com solicitante se necessário); confirmação humana fundamentada. Não alterar código nem negar automaticamente. Ausência de histórico oncológico isoladamente não comprova divergência. PET-CT pertinente segue análise DUT 60; procedimento distinto fica fora do escopo, com regularização na origem quando cabível.

## REQ-04/12/12.1/12.2 — Integração SIGO/Oracle
- Um conector lógico simulado, unidirecional, somente leitura, duas fontes: AMM (Análise Médica) e AMOP (Operacional). AUD totalmente fora do escopo; não consultar. Não integrar fidelização ou outros setores. Não reproduzir interfaces completas SIGO nem integrar Oracle/MV/TASY reais; preservar código futuro existente.
- Nova guia só entra pela primeira presença na AMM. Não importar guia inédita exclusivamente na AMOP. Após entrada, monitorar AMM e AMOP, consolidar registro único, preservar identidade, histórico, documentos e SLA em movimentações.
- Atualização manual e sincronização automática em segundo plano (independente de aba aberta), periodicidade configurável administrativamente, evitar execuções concorrentes duplicadas; deduplicar, atualizar localização/documentação, tratar falhas e consultas incompletas, registrar eventos. Reutilizar arquitetura existente. Nenhuma escrita, autorização, negativa, alteração cadastral ou movimentação no SIGO.

## REQ-05 — Pendência de codificação
Divergência confirmada pelo médico: acompanhamento em fila/card próprio (fora do escopo — divergência cadastral confirmada quando aplicável); permanece operacionalmente pendente enquanto presente na AMM ou AMOP. Qualquer médico autorizado pode acompanhar/assumir; filtro minhas pendências sem poluição visual. Correção e liberação feitas na origem; distinguir declaração manual de confirmação técnica; correção isolada sem liberação não encerra acompanhamento. Preservar justificativa, autoria, histórico, SLA. Não contar divergência como autorização/negativa PET-CT. Ausência nas duas filas segue REQ-16.1, sem presumir resultado da regularização.

## REQ-06 — Governança
Registrar backend: usuário, operadora, guia, ação, data/hora, estado anterior/posterior, origem, sincronizações/falhas, assunções/devoluções, responsabilidade, reativações. Distinguir confirmação na origem de ação declarada; não atribuir ao usuário que sincroniza ações de terceiros no SIGO. Logs técnicos, login e trilha administrativa exclusivamente para administradores autorizados (RBAC backend, isolamento). Médico vê dados operacionais/clínicos pertinentes, não logs. Não criar novo painel administrativo agora.

## REQ-07/19 — Cards e produtividade
Seis cards clicáveis, com contagens dinâmicas (sem números hardcoded):
| Card | Descrição/semântica |
|---|---|
| Solicitações | Guias importadas — demanda compartilhada |
| Aguardando análise | Guias disponíveis ainda não iniciadas — demanda compartilhada |
| Em análise | Análises iniciadas pelo médico autenticado e não finalizadas |
| Pendências de codificação | Guias aguardando correção e liberação no sistema da operadora |
| Pendências documentais | Guias aguardando documentação complementar |
| Concluídas | Análises finalizadas por você |
- Cards filtram tabela. Concluídas é produtividade individual do login no período, sem subdivisão confirmadas/aguardando SIGO. Ao clicar, mostrar registros históricos correspondentes, sem reinseri-los na fila ativa. Não comparar médicos nem criar seletor de equipe. Contagem individual por atuação, sem duplicar finalizações.
- Período discreto: Hoje (padrão), Últimos 7 dias, Mês atual, Personalizado. Não esconder pendências anteriores ao período na fila operacional. Não criar regras adicionais de métrica sem documentar eventual ambiguidade.

## REQ-08/09/09.1 — Concorrência e responsabilidade
Ao assumir (Analisar, ou ação equivalente de reanálise), bloqueio atômico backend por guia/operadora: somente responsável edita/finaliza; demais visualizam em leitura. Devolver à fila na tela individual preservando trabalho e SLA; permitir continuidade por outro médico. Liberação automática por inatividade configurável administrativamente, rejeitar sessão obsoleta, preservar trabalho, avisar quando possível. Tempo exato não aprovado: 30 min é apenas proposta; se indispensável no demo, documentar valor provisório configurável. Logs técnicos somente admin.

## REQ-10 — Acionamento IA
Importação: somente identificação, triagem terminológica/documental preliminar, possíveis divergências, deduplicação e dados SLA. Análise clínica-regulatória DUT 60 apenas quando médico assume e inicia análise. Recomendação/alternativa quando pertinente, revisão humana obrigatória, nenhuma decisão autônoma. Não redesenhar tela individual nesta fase.

## REQ-11/11.1/11.2/11.3 — Pendências documentais
- Card próprio. Identificar documentos faltantes pertinentes ao caso, permitir conferência médica (incluindo histórico hospitalar externo), preservar evidências e análises. Fluxo de solicitação de complementação validado pelo médico, envio manual ao operacional. Não automatizar comunicação nesta etapa.
- Iniciar prazo estimativo operacional de 48h configurável quando médico registra encaminhamento ao operacional (não ao identificar falta ou gerar minuta). Não comprova recebimento pelo paciente; não suspende/reinicia SLA regulatório; não gera negativa automática.
- Vencimento sinaliza reavaliação; documentos novos sinalizam reanálise. Sincronizar documentos na origem, preservar anteriores e leitura de fotos/prints/PDF digitalizado existente; fluxo completo de recebimento/upload ainda a validar, não redesenhar agora. Acompanhar permanência/saída conforme REQ-16.1. Automação futura de mensagens WhatsApp/e-mail/telegrama, acompanhamento de respostas, integração operacional após aprovação humana, notificações e LGPD.

## REQ-13 — SLA
Ordenação padrão: vencidos, próximos do vencimento, dentro do prazo, protocolo ausente/dados insuficientes (visíveis). Dentro das categorias, vencimento mais próximo primeiro. Ordenação crescente/decrescente somente na coluna SLA. Data original do protocolo do beneficiário é base do cálculo, distinta da data de entrada na operadora usada para identidade. Não reiniciar/suspender automaticamente por transferências, pendências, mudança de médico ou reativação. Não inventar datas, prazos legais ou regras arbitrárias; reutilizar regras validadas existentes. Documentar eventuais lacunas.

## REQ-14 — Pesquisa
Único campo: Buscar código do beneficiário. Retornar guias do código informado, respeitando RBAC e tenant. Não pesquisar por nome/número da guia. Sem setas de ordenação nessas colunas.

## REQ-15 — Atualização
Bloco Integração com a operadora — SIGO/Oracle: botão Atualizar solicitações, data/hora da última sincronização bem-sucedida, estado em andamento e falha discreta. Detalhes técnicos só admin. Falhas não retiram guias.

## REQ-16 — Tabela e ações
Colunas na ordem: Nº da guia; Código do beneficiário; Procedimento; Situação SLA (única ordenável); Data limite; Status da análise; Pendência documental; Médico auditor; Localização; Ações. Localização AMM/AMOP ou presença simultânea, sem duplicar registro. Sem última movimentação, sem menu de três pontos, sem filtros permanentes não aprovados. Cabeçalho fixo, scroll vertical interno, sem scroll horizontal no viewport desktop de referência; readequar larguras e manter legibilidade.
| Situação | Ação contextual única |
|---|---|
| Aguardando análise | Analisar |
| Em análise pelo usuário | Continuar |
| Em análise por outro médico | Visualizar (somente leitura) |
| Pendência de codificação | Regularizar |
| Pendência documental | Acompanhar |
| Novos documentos | Reanalisar |
| Prazo de complementação vencido | Reavaliar |
Botões funcionais respeitando RBAC e concorrência. Sem ações de escrita na origem.

### REQ-16.1 — Saída da fila
Retirar automaticamente da fila ativa somente quando ausência em AMM E AMOP for confirmada por sincronização completa e bem-sucedida de ambas (não inferir a partir de erro, paginação incompleta ou ausência não confiável). Preservar histórico, não presumir autorização/negativa/conclusão médica. Análise finalizada no AuditIA que permanece na origem conserva vínculo operacional até condição de saída, sem dupla finalização. Ação específica para essa condição não foi definida; não inventar novo fluxo médico, registrar lacuna caso necessário.

### REQ-16.2 — Reativação
Reaparecimento na AMM ou AMOP de guia previamente importada e retirada: confirmar cumulativamente mesma operadora, número da guia, código do beneficiário, pedido médico original integralmente correspondente, data original de entrada no sistema da operadora. Número sozinho não basta. Complementos não alteram por si a identidade do pedido. Se todos correspondem, reativar registro anterior preservando SLA, documentação, análises, autoria; não contar como nova solicitação. Divergência ou ausência de informação: conferência humana, sem reativação ou duplicação automática. Não mapear outros setores.

## REQ-17/18 — Flexibilidade
Médico pode acompanhar e antecipar análise/reanálise de guias previamente importadas na AMOP, além da AMM. Novos documentos ou prazo vencido habilitam reanálise/reavaliação conforme regras. Qualquer médico autorizado disponível pode assumir reanálise, independente do anterior; manter histórico, produtividade individual, concorrência e SLA. Não exigir retorno à AMM para atuar.

## REQ-20/21 — Personalização
Saudação substitui título atual sem ampliar altura: “Olá, Dra. Marina!” / “Bem-vinda ao AuditIA. Acompanhe suas solicitações e os prazos regulatórios.” Usar primeiro nome autenticado e tratamento cadastrado, neutro se ausente; não inferir gênero pelo nome. Tipografia original.
Coluna Médico auditor: responsável atual com subtítulo “Responsável atual”; se disponível/pendente após avaliação, último médico com “Última análise”; travessão se nunca analisada. Atualizar responsável ao assumir, preservando autoria anterior.

## REQ-22/22.1 — Warm Glass
Preservar logo, tipografia Aetherfield, navegação original sem sidebar, hierarquia, botões pretos, layout compacto e responsivo. Não adotar elementos de mockups não aprovados. Alterações visuais somente dashboard médico, não landing/login/termo/outras telas. Seis cards em uma linha desktop quando couber, adaptação responsiva. Preservar dimensões/arredondamentos originais.
Tokens: #E4DBCF, #F5F1EB, #E9DFD1, neutro funcional #F7F3E6, amarelo #FFF546, preto #111111. Fundo dashboard: `linear-gradient(135deg, #E4DBCF, #F5F1EB 65%, #E9DFD1)`.
Glass somente nos seis cards e bloco de integração; não na tabela, cabeçalho ou navegação. Opacidade 7%, blur 2px, sombra 25%. Destaque amarelo exclusivamente Pendências documentais. Classe compartilhada, escopada ao dashboard, fallback legível sem backdrop-filter, foco teclado/cliques preservados.

```css
.glass-panel {
  background: rgba(255, 255, 255, 0.07);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  border: 1px solid rgba(255, 255, 255, 0.65);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.5),
    inset 0 -1px 0 rgba(255, 255, 255, 0.1),
    inset 0 0 8px 4px rgba(255, 255, 255, 0.4);
  position: relative;
}
.glass-panel::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0;
  height: 1px; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.8), transparent);
}
.glass-panel::after {
  content: ''; position: absolute; top: 0; left: 0;
  width: 1px; height: 100%; pointer-events: none;
  background: linear-gradient(180deg, rgba(255,255,255,0.8), transparent, rgba(255,255,255,0.3));
}
.glass-panel--highlight { background: rgba(255, 245, 70, 0.42); }
```

## REQ-23 — Warm Muted funcional
| Indicador | Fundo | Texto | Contorno |
|---|---|---|---|
| Prazo excedido | #F7F3E6 | #C51D0D | #F31908 |
| Próximo do vencimento | #F7F3E6 | #806000 | #FCC100 |
| Dentro do prazo | #F7F3E6 | #007A10 | #00A815 |
| Em análise | #F7F3E6 | #0250EA | #0250EA |
| Pendência documental | #FDF691 | #776020 | #776020 |
| Pendência de codificação | #F7F3E6 | #80573D | #80573D |
| Protocolo ausente | #F7F3E6 | #625D57 | #625D57 |
Indicadores compactos com contorno e rótulos textuais, não apenas cor. Validar WCAG AA na renderização real, documentar divergências para PO, não substituir silenciosamente HEX.

## Dados de demonstração
Priorizar B01 (atende DUT 60), B02 (documentação insuficiente), B07 (PET-CT cerebral/demência, fora do escopo DUT 60, sem negativa automática). Preservar demais casos existentes para histórico/testes; não apagar nem inventar dados/datas de registros existentes. Fixtures adicionais explicitamente sintéticas apenas se necessárias (movimentação, duplicidade, reativação, pendências, concorrência, falhas).

## Critérios de testes e aceite
Executar baseline e regressão existente, adicionar cobertura por requisito e registrar comandos/resultados reais, sem declarar aprovação sem execução.
- Integração: entrada AMM, exclusão AUD, exclusão AMOP inédita, presença simultânea, movimentação, falhas parciais/consultas incompletas, ausência confirmada, histórico, reativação válida e divergente/insuficiente, idempotência, SLA, atualização manual/automática, documentos.
- Segurança: autenticação, RBAC backend, isolamento operadoras, logs admin, assunção simultânea, devolução, inatividade, sessão obsoleta, nenhuma escrita origem.
- Fluxo: pendências documentais/codificação, início 48h, vencimento sem negativa, reanálise outro médico/AMOP, histórico, produtividade sem duplicação, IA só análise após ação médica, fora escopo sem negativa automática.
- Dashboard: seis contagens, filtros por card e período, pendências antigas visíveis, produtividade individual, pesquisa exclusivamente beneficiário, ordenação SLA, ações contextuais, saudação, responsabilidade atual/última, localização, ausência menu três pontos/última movimentação, histórico concluídas separado da fila ativa, responsividade, teclado, contraste, glass nos componentes corretos, regressão visual outras telas.

## Documentação, backlog e checkpoint
Atualizar PROJECT_STATE.md, DESIGN.md, AGENTS.md apenas regras persistentes necessárias, especificação e checklist. Backlog: integração bidirecional/real, outras DUTs, comunicação documental automatizada, motor terminológico ampliado, tempo de inatividade, validação completa recebimento documental, beta operadora.
Ao final informar diagnóstico, reaproveitamento, implementações, requisitos testados/bloqueados, arquivos, migrações, comandos e resultados, limitações/riscos, URL local, Git status e hash do checkpoint local caso testes satisfatórios. Não commitar segredos/bancos. Não push/merge/deploy. Implementação não equivale a aceite; PO valida funcional e visualmente antes de avançar.

**MARCADOR DE INTEGRIDADE — FIM DA ESPECIFICAÇÃO REQ-01 A REQ-23**
