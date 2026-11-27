# AuditIA — Especificação Mestre Beta 0.2

**Estado:** proposta de implementação para aprovação humana. **Data:** 23/11/2026. **Fonte técnica:** inspeção do `mvp.zip` enviado nesta conversa. **Escopo:** MVP web privado com uma operadora fictícia, três casos sintéticos e DUT 60. **Não é sistema de autorização automática.**

## 1. Instrução principal ao GitHub Copilot

Você está trabalhando em um projeto EXISTENTE. NÃO reescreva o aplicativo, NÃO substitua os bancos existentes, NÃO modifique `main`, NÃO remova testes ou rotas sem verificar suas dependências e NÃO implemente tudo em uma única etapa. Leia esta especificação, inspecione os arquivos reais, execute a suíte atual e apresente um plano com diffs previstos. Aguarde aprovação antes de editar. Em cada etapa, mostre arquivos alterados, testes, limitações e evidências do resultado. Preserve os fluxos clínicos, regulatórios, de autenticação e de rastreabilidade que já funcionam. Não utilize dados reais de pacientes.

## 2. Inventário confirmado do ZIP

- `mvp/app.py`: inicialização da aplicação.
- `mvp/backend/app.py`, `auth.py`, `storage.py`, `consultas.py`: API, segurança e persistência.
- `mvp/backend/adapters.py`: conectores **demonstrativos** SIGO, MV e Tasy; não há integração real. Atualmente `demo_raw()` gera uma guia por origem; `normalize()` mantém `guide_received_at` se presente.
- `mvp/backend/datas.py`: fuso `America/Sao_Paulo`, feriados nacionais BR e `sla_guia(entrada, fim)`; atualmente retorna dias úteis decorridos, não prazo restante ou vencimento.
- `mvp/frontend/fila.py`: apresenta data de entrada e SLA decorrido.
- `mvp/backend/homologacao.py`: bateria sintética com B01, B02, B07 e outros cenários; não recriar IDs.
- `mvp/backend/criterios_dut.py`, `engine.py`, `regulatoria.py`, `fonte_ans.py`, `vigencia.py`, `tuss_rol.py`: regras e governança regulatória; preservar e auditar.
- `mvp/frontend/`, `mvp/frontend/static/`: interface existente.
- `mvp/tests/`: testes existentes; ampliar, não substituir.
- `mvp/BETA.md` e `mvp/LEIA-ME.md`: documentação vigente da versão anterior, contendo fluxo gerencial a atualizar.
- `mvp/auditia-beta.sqlite3` e `mvp/auditia-governanca-demo.sqlite3`: bases de demonstração. NÃO sobrescrever; criar cópia de segurança e usar banco temporário para testes.
- `mvp/assets/documentos/`: documentos de demonstração. Não presumir que todos são seguros; verificar metadados, nomes, texto e imagens antes de reutilizar.

**Achado importante:** `LEIA-ME.md` descreve que registrar revisão encaminha o caso automaticamente para `Gerência`; `BETA.md` lista `/gerencia` e `/pacote/{id}`. A retirada do módulo requer análise de transições, navegação, rotas, permissões, testes e persistência, não apenas CSS.

## 3. Escopo da Beta 0.2

### Incluído

1. Aplicação web local/privada; uma única operadora **fictícia** (identidade e marca inventadas); login Auditor e Admin.
2. SIGO/Oracle **simulado**, sem credenciais, conexão ou alegação de interoperabilidade real.
3. Importação explicitamente acionada pelo auditor por botão **Importar guias do SIGO**.
4. Detecção de solicitações PET-CT independentemente de tabela de origem: TUSS, AMB e tabela interna fictícia, **somente quando mapeamentos estiverem homologados**. Código desconhecido/descrição ambígua → revisão manual; nunca ignorar silenciosamente.
5. Importação de todas as guias pendentes elegíveis, inclusive antigas, com deduplicação idempotente por operadora + origem + ID externo. Resumo: encontradas, importadas, já existentes, para revisão, erros.
6. Fila com protocolo original, cadastro no SIGO, importação, procedimento, código, tabela, SLA decorrido, restante, prazo e situação; datas em DD/MM/AAAA.
7. Três casos sintéticos **B01, B02, B07**, com documentos e gabaritos revisados.
8. DUT 60 versionada, conferência de evidências, extração documental, parecer de apoio, revisão e decisão médica, rastreabilidade.
9. Admin essencial: usuários, versão homologada da DUT, histórico/auditoria.
10. Tratamento explícito de erros de origem, indisponibilidade do modelo e dados insuficientes.

### Fora do escopo (reservado para versões futuras)

- Discussão de casos com gerência, fila gerencial, encaminhamento gerencial automático, comentários e PDF de pacote gerencial.
- Integração real com SIGO/Oracle, MV ou Tasy.
- Autorização, negativa ou atualização transacional automática na operadora.
- Uso de prontuários ou dados identificáveis reais.
- Expansão para outras DUTs e uso clínico em produção.

**Política de preservação:** retirar o módulo gerencial da experiência ativa sem apagar registros históricos nem destruir código reutilizável. Se possível, isolar por feature flag desabilitada; remover transição automática após revisão; garantir que a revisão permaneça no fluxo do auditor. Rotas antigas devem ser inacessíveis no modo Beta 0.2 ou explicitamente desabilitadas, com testes de autorização. Não deixar endpoints ativos apenas porque o menu está oculto.

## 4. Casos sintéticos e gabaritos

| Caso | Situação | Saída técnica esperada | Restrição |
|---|---|---|---|
| B01 | PET-CT oncológico, linfoma com comprovação e finalidade de estadiamento, documentos completos | `CRITERIOS_ATENDIDOS` / recomendação favorável à revisão | Validar subitem exato da DUT 60 e todos os requisitos antes de fixar gabarito |
| B02 | PET-CT oncológico, indicação/diagnóstico e/ou documentos indispensáveis ausentes | `DADOS_INSUFICIENTES` / pendência documental específica | Não gerar negativa automática por ausência de documento |
| B07 | PET cerebral FDG para investigação de demência, sem finalidade oncológica | `INDICACAO_NAO_CONTEMPLADA_NA_DUT60` / encaminhamento humano | Não concluir ausência de cobertura geral; verificar outras bases |

Preservar os IDs B01/B02/B07 existentes em `homologacao.py`. Não copiar dados de pacientes reais nem converter pareceres históricos em verdade regulatória. Criar pedidos, relatórios e laudos **novos e integralmente fictícios**, com datas e identificadores artificiais. Documentar em separado o gabarito clínico-regulatório, os critérios e a versão normativa; não enviar gabarito ao modelo como parte do caso.

**Nota:** o `homologacao.py` atual aponta B01 para `60.2.a`, B02 para pendência e B07 para fora de escopo. Isso é configuração do projeto, não validação independente da norma. Conferir com Anexo II vigente e a versão aplicável antes de aprovar os resultados.

## 5. Datas e SLA

- `data_protocolo_operadora`: data original de protocolo do pedido pelo paciente. **Única referência inicial do SLA**.
- `data_cadastro_sigo`: momento em que a guia foi registrada no sistema simulado; não reinicia SLA.
- `data_importacao_auditia`: momento da importação; não reinicia SLA.
- `data_limite_resposta`, `dias_uteis_decorridos`, `dias_uteis_restantes`, `status_sla`: campos derivados por cálculo determinístico, não pelo Gemini.
- Exibir também origem, referência normativa e tipo de prazo: **resposta conclusiva** versus **garantia de atendimento**, que não são intercambiáveis.
- Regra de prazo inicialmente proposta para PAC: **10 dias úteis**, sujeita à validação jurídica/regulatória da RN ANS 623/2024, aplicabilidade ao canal e regras de contagem. Não codificar como prazo universal sem confirmação. A RN 566/2022 trata de garantia de atendimento, com obrigações distintas.
- Fuso `America/Sao_Paulo`; feriados nacionais e locais configuráveis; testar datas-limite, finais de semana, feriados, protocolo fora do horário e início da contagem. A política de contagem deve estar explicitamente documentada.
- Ausência da data original de protocolo: `PROTOCOLO_AUSENTE`, pendência visível e impossibilidade de afirmar SLA válido. Nunca substituir silenciosamente pela data do SIGO.
- Fila: vencidas primeiro; depois ordenar por SLA consumido de forma decrescente; empates por protocolo mais antigo e ID estável. Definir comportamento de prazo desconhecido.
- Manter compatibilidade com `guide_received_at` somente após determinar sua semântica real em cada origem; não renomear o campo e assumir que é protocolo.

## 6. Importação e normalização

- `adapters.py` é o ponto de partida, mas o conector atual fornece uma guia fictícia por origem; adaptar o simulador para as três guias, sem alterar APIs públicas desnecessariamente.
- Criar catálogo de correlações com `tabela_origem`, `codigo_origem`, `descricao_origem`, `codigo_canonico`, `tipo_procedimento`, `fonte_mapeamento`, `versao`, `status_homologacao`.
- Não inventar códigos oficiais AMB/TUSS. Para demonstrar códigos internos, usar códigos claramente fictícios (`SIM-PET-001`, etc.). Se usar TUSS real, conferir na correlação oficial vigente e preservar código/descrição de origem.
- PET com FDG não é necessariamente oncológico. B07 não pode ser classificado como oncologia só por radiofármaco.
- Procedimentos acessórios (revisão, TC complementar, relatórios) não devem ser equiparados ao PET-CT principal.
- Sem correspondência inequívoca: `REVISAR_CLASSIFICACAO`, manter guia visível; erro técnico: `FALHA_IMPORTACAO`, não apresentar fila vazia como sucesso.
- Importação repetida não duplica guia, anexos ou eventos de negócio; registrar tentativas de sincronização e erros sem exposição de dados sensíveis.

## 7. Segurança e governança

- Modo estritamente sintético, acesso local; não publicar serviço na internet.
- Segregação de perfis e operadora; validar autorização no backend, não apenas na UI.
- Não inserir chaves em repositório, prompts ou logs; usar `.env` local ignorado pelo Git.
- Não enviar documentos reais à API Gemini. O protótipo atual envia textos sintéticos ao serviço externo: isso deve ser informado na interface e no termo.
- Resposta do modelo é texto não confiável; não executa comandos nem modifica regras normativas.
- Regras da DUT e cálculo do SLA são determinísticos/versionados; IA apenas extrai, organiza e apoia interpretação sob revisão humana.
- Guardar origem documental, hash, versão da regra, modelo, momento, evidências e revisão; não afirmar que a trilha é inviolável.
- Não usar porcentagem de confiança não calibrada como validação clínica. Se faltar prova decisiva, marcar incerteza e solicitar revisão.

## 8. Plano incremental de implementação

### Etapa 0 — Diagnóstico (SEM alterações)

- Confirmar branch, estado do Git, dependências e suíte de testes.
- Mapear endpoints, chamadas da UI, tabelas e transições da gerência; dependências da revisão médica.
- Confirmar schema real das guias e significado de `guide_received_at`.
- Conferir dados e anexos sintéticos, possíveis identificadores e conflitos de documentação.
- Entregar inventário de reutilização, riscos, arquivos a alterar e plano de rollback. **Aguardar aprovação.**

### Etapa 1 — Desacoplar gerência

- Remover da navegação e do fluxo ativo, desabilitar endpoints relacionados no modo beta, retirar redirecionamento após revisão.
- Preservar revisão médica e histórico; migrar dados apenas se necessário e com backup.
- Testar que revisão não encaminha à gerência e que endpoints gerenciais não ficam acessíveis.

### Etapa 2 — Modelo temporal e SLA

- Acrescentar protocolo original, cadastro SIGO, importação e campos derivados; migração não destrutiva.
- Implementar cálculo determinístico e calendário configurável; validar norma e contagem antes de ativar prazo.
- Testes de dias úteis, feriados, vencimento, ausência de protocolo e ordenação.

### Etapa 3 — Conector SIGO simulado

- Normalizar B01/B02/B07, códigos/tabelas, detecção segura e importação explícita.
- Deduplicação, atualização controlada, importação de guias antigas, falha e resumo.
- Testar reimportação e não perda de guias ambíguas.

### Etapa 4 — Documentos e DUT 60

- Inspecionar os anexos atuais e substituí-los por documentos integralmente fictícios quando necessário.
- Validar gabaritos B01/B02/B07 contra a norma versionada e separar pendência de não enquadramento.
- Preservar extração, parecer, revisão humana, logs e erros explícitos.

### Etapa 5 — UI, documentação e aceite

- Interface enxuta com fila, guia, documentos, evidências, parecer e revisão.
- Atualizar `LEIA-ME.md`, `BETA.md` e testes, removendo instruções gerenciais do fluxo atual.
- Rodar suíte completa e teste manual ponta a ponta; produzir evidências e checklist de aceite.

## 9. Critérios mínimos de aceite

1. Importar B01/B02/B07 de SIGO simulado; nenhuma guia omitida silenciosamente.
2. Repetir importação sem duplicação; falha do conector gera erro visível.
3. Fila usa protocolo original; cadastro e importação não alteram início do SLA.
4. Fila ordena vencidas/mais antigas primeiro, com datas em formato brasileiro.
5. B01: critérios comprovados → recomendação favorável, **somente após validação da DUT**.
6. B02: falta decisiva → pendência, sem negativa automática.
7. B07: fora da DUT 60 oncológica, sem conclusão automática sobre cobertura geral.
8. Revisão médica é persistida sem redirecionar ou encaminhar à gerência.
9. Menu/rotas gerenciais indisponíveis na Beta 0.2; histórico preservado.
10. Sem chamadas reais ao SIGO/MV/Tasy; nenhum dado real; sem autorização transacional.
11. Testes existentes continuam passando; novos testes cobrem regressões e limites.
12. Versão e origem das regras, evidências, modelo e revisão são rastreáveis.

## 10. Comando de início para o Copilot

> Leia integralmente `AuditIA_Beta_0_2_ESPECIFICACAO_MESTRE.md` e inspecione a estrutura real do projeto. Execute apenas a **Etapa 0 — Diagnóstico**, sem editar arquivos. Liste o que já existe, identifique conflitos e dependências, mostre os arquivos exatos envolvidos, o estado da suíte de testes, os riscos de migração e um plano de mudanças incremental. Não inicie a Etapa 1 até minha aprovação explícita.

## 11. Pendências de validação antes de declarar pronto

- Verificar texto oficial e vigência aplicável da DUT 60, inclusive o subitem do B01.
- Confirmar norma, marco inicial, contagem e abrangência do prazo de resposta conclusiva, sem confundir com garantia de atendimento.
- Verificar os códigos TUSS contra o arquivo oficial de correlação atualizado; não aceitar códigos demonstrativos como prova de cobertura.
- Inspecionar integralmente anexos e bases de demonstração para assegurar ausência de dados reais.
- Testar localmente na máquina do usuário; esta especificação não afirma que o aplicativo foi executado ou que todos os testes passaram.
