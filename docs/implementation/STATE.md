# AuditIA — Estado de Execução da Implementação (STATE.md)

**Última atualização:** 26/11/2026  
**Branch:** `feature/aetherfield-design-system`  
**Checkpoint base:** `7e87889`  
**Fase atual concluída:** Fases 3 e 4 (Sessões 03 e 04 — REQ-05, REQ-07, REQ-11 a REQ-23)

---

## 1. Status Geral da Fase 1

Todos os requisitos da Fase 1 foram integralmente implementados, integrados e validados por suítes de testes automatizados dedicados e testes de regressão:

- **REQ-01 (Produtividade individual do médico auditor):** Centralizada em `mvp/backend/consultas.py` (`produtividade_individual`), aferindo exclusivamente casos finalizados pelo auditor autenticado na sessão (`case_workflow` canônico com fallback estrito ao último autor de review médica). Elimina qualquer risco de dupla atribuição entre médicos ou dupla contagem entre revisões e finalizações.
- **REQ-02 (Variantes de grafia do PET-CT e triagem):** Em `mvp/backend/tuss_rol.py`, detecção de variantes textuais (`pet-ct`, `pet ct`, `pet/ct`, `pet-tc`, `pet tc`, `pet scan`, `petscan`, `tomografia por emissao de positrons`). Sugere código provável quando há indicação clínica sem forçar equivalência automática; sinaliza pedidos sem código oficial para conferência humana obrigatória; assegura que ausência de histórico oncológico isoladamente não gera divergência cadastral.
- **REQ-03 (Proveniência e integridade cadastral):** Preservação dos campos originais da guia, sistema de origem, códigos associados e proveniência sem perda de dados na ingestão.
- **REQ-04 (Conector SIGO e separação de filas):** Conector lógico simulado em `mvp/backend/sigo_simulado.py` e persistência em `mvp/backend/storage.py`. Leitura restrita a AMM e AMOP; exclusão total de registros da fila AUD; novas guias entram exclusivamente pela primeira presença comprovada na AMM.
- **REQ-11.3 (Preservação de anexos binários):** Preservação dos blobs binários originais (PDFs, PNG, JPG, JPEG) com seus respectivos hashes SHA-256 e entrega íntegra para download/visualização inline.
- **REQ-12 (Consolidação em registro único):** Guia que transita de AMM para AMOP tem sua localização atualizada mantendo chave primária e histórico únicos, sem gerar duplicidade.
- **REQ-12.1 (Guarda de concorrência em segundo plano):** Em `mvp/backend/app.py`, bloqueio `_sync_locks` com rejeição HTTP `409 Conflict` contra disparos simultâneos duplicados de sincronização no mesmo tenant.
- **REQ-12.2 (Tratamento de falhas e savepoints):** Sincronizações operam com `SAVEPOINT` e rollback atômico, impedindo inconsistência no banco de dados em falhas parciais.
- **REQ-15 (Timestamp de sincronização):** Exibição da data/hora da última sincronização bem-sucedida no card colapsável de integração da página principal.
- **REQ-16.1 (Regra de saída de fila):** Guia é retirada da fila ativa (`removido_origem_em` preenchido e filtrada de `casos_da_operadora`) somente após ausência confirmada simultaneamente em AMM e AMOP por sincronização válida e completa.
- **REQ-16.2 (Reativação cumulativa de guias):** Reativação automática estrita exigindo validação cumulativa dos 5 critérios (tenant, external_id, beneficiary_code, data_protocolo_operadora original e hash integral do pedido médico). Caso haja divergência no pedido médico, a reativação é bloqueada, registrando evento de governança e sinalizando divergência cadastral.

---

## 2. Fase 2 Concluída (Sessão 02 — Bloqueio Atômico e Concorrência)

- **REQ-08 (Assunção e Bloqueio Atômico):** Implementado no SQLite com `UPDATE cases` condicional atômico (`assumir_caso`). Concorrência real protegida sem conflitos de leases.
- **REQ-09 / REQ-09.1 (Devolução à Fila e Expiração de Inatividade após 60 min):**
  - Trava expira após 60 minutos de inatividade (`AUDITIA_LOCK_TIMEOUT_MINUTES`, padrão 60 min).
  - Expiração automática limpa a trava mantendo `responsavel_anterior` e trilha de governança.
  - Renovação automática em atividades clínicas válidas (`renovar_trava_caso` em parecer, revisão, minuta).
  - Devolução voluntária à fila via `POST /caso/devolver`, liberando a trava e preservando integralmente pareceres e rascunhos.
- **REQ-10 (Validação de Posse de Trava no Backend):** Rotas de alteração (`/caso/finalizar`, `/parecer`, `/analisar`, `/revisar`, `/caso/minuta/*`) barram médicos não detentores da trava ativa com HTTP 403 Forbidden.
- **REQ-18 (Continuidade da Auditoria):** Outro médico auditor pode assumir guias expiradas ou liberadas, preservando o histórico de análises do responsável anterior.
- **REQ-21 (Exibição da Coluna Médico Auditor):** Exibe "Responsável atual" quando sob trava ativa, "Última análise: [Médico]" após devolução/expiração, ou "—" quando pendente sem responsável.
- **Integração de UI:** Botão "Analisar" no dashboard direciona via `POST /caso/assumir`; tela `/caso/<id>` exibe banner de trava com opção de "Devolver à fila" para o titular da trava e alerta de somente-leitura para terceiros.

---

## 3. Fases 3 e 4 Concluídas (Sessões 03 e 04 — Dashboard Funcional e Warm Glass/Muted)

- **REQ-05 (Pendências de Codificação):** Acompanhamento em card próprio de divergências cadastrais/terminológicas confirmadas, permanecendo operacional enquanto em AMM/AMOP.
- **REQ-07 (Grid de 6 Cards Dinâmicos):** 6 cards clicáveis (`Solicitações`, `Aguardando análise`, `Em análise`, `Pendências de codificação`, `Pendências documentais` com destaque amarelo, `Concluídas`). Clique filtra dinamicamente a tabela sem reinserir casos concluídos na fila ativa.
- **REQ-11 / REQ-11.1 / REQ-11.2 (Gestão Documental e Timer de 48h):** Separação documental, cálculo de prazo estimativo operacional de 48h sem alterar SLA regulatório da ANS nem gerar negativa automática. Encaminhamento manual via interface (`POST /caso/encaminhar-complementacao`). Vencimento do prazo sinaliza ação "Reavaliar"; novos documentos sinalizam ação "Reanalisar".
- **REQ-13 (SLA Regulatório):** Ordenação padrão por urgência de SLA e suporte a alternância crescente/decrescente exclusivamente na coluna de SLA.
- **REQ-14 (Pesquisa Unificada):** Campo único para buscar código de beneficiário, preservando RBAC e isolamento multi-tenant.
- **REQ-16 / REQ-17 (Tabela e Ações Contextuais):** Tabela com 10 colunas (incluindo Localização AMM/AMOP); botões contextuais únicos por estado (`Analisar`, `Continuar`, `Visualizar`, `Regularizar`, `Acompanhar`, `Reanalisar`, `Reavaliar`, `Revisar`); médico pode atuar na AMOP.
- **REQ-19 (Filtros por Período Discreto):** Filtros "Hoje (padrão)", "Últimos 7 dias", "Mês atual" e "Todo o período", apurando produtividade individual sem ocultar pendências operacionais ativas.
- **REQ-20 (Saudação Personalizada):** Saudação personalizada com primeiro nome e tratamento cadastrado ("Dra./Dr."), com fallback neutro, sem expandir a altura visual.
- **REQ-22 / REQ-22.1 (Design System Warm Glass):** Gradiente de fundo escopado ao dashboard (`#E4DBCF`, `#F5F1EB`, `#E9DFD1`), painéis `.glass-panel` com opacidade 7%, blur 2px e sombra nos 6 cards e bloco de integração, com destaque amarelo em pendências documentais.
- **REQ-23 (Badges Warm Muted Funcionais):** Badges com contorno e contraste WCAG AA conforme os 7 estados da especificação.

---

## 4. Validação dos Testes

- **`mvp.tests.test_fase34_dashboard`:** 4/4 aprovados.
- **`mvp.tests.smoke_dashboard`:** Smoke test de ponta a ponta do dashboard autenticado com dados sintéticos aprovado (HTTP 200 OK).
- **`mvp.tests.test_produtividade_individual`:** 6/6 aprovados.
- **`mvp.tests.test_fase2_concorrencia`:** 6/6 aprovados.
- **`mvp.tests.test_workflows`:** Testes de regressão do dashboard aprovados.
- **Status da suíte:** 100% de sucesso sem falhas ou erros.
