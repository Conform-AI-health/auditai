# AuditIA · protótipo com parecer com Gemini
Demonstração com casos exclusivamente sintéticos. A aplicação encaminha a guia e os documentos textuais à API Gemini do Google, com a DUT 60 transcrita da fonte fornecida e a correlação TUSS do projeto. O histórico fica no SQLite local. Somente os lotes das operadoras e seus desfechos são simulados. O histórico de versões anterior está em docs/.
## Organização do projeto

- [backend/](backend/) contém a API REST em Python, autenticação JWT, banco de dados, integração com o Gemini, regras da DUT e geração de PDF.
- [frontend/](frontend/) contém o HTML e o JavaScript que consome os endpoints `/api`. O Bootstrap, o CSS e os scripts ficam em [frontend/static/](frontend/static/).
- [app.py](app.py) inicia o serviço que atende as duas camadas. Na beta, use [Iniciar_Beta.cmd](Iniciar_Beta.cmd).

## Preparar no Windows
1. Instale Python 3.10+. Use uma pasta nova para extrair o pacote.
2. No arquivo `.env` da raiz do projeto, preencha `GEMINI_API_KEY=` com sua chave e salve. `AUDITIA_MODELO` permite escolher o modelo. No primeiro início, a aplicação cria `AUDITIA_JWT_SECRET` nesse mesmo arquivo quando a variável ainda não existe. Para ativar o leitor de PDF com texto, execute `py -3 -m pip install -r requirements.txt`. TXT UTF-8 funciona apenas com a biblioteca padrão.
3. Abra `Iniciar.cmd`, guarde as senhas exibidas e entre como `auditor-aurora`. Deixe o terminal aberto. A URL é http://127.0.0.1:8765. A cada login, o auditor deve aceitar o termo da beta antes de acessar os casos.
4. Na tela **Casos**, use **Importar casos fictícios — SIGO** ou **Importar casos fictícios — MV** para carregar os lotes demonstrativos. Os conectores não acessam sistemas reais. A lista carrega até 20 casos por página e oferece navegação **Anterior** e **Próxima**.
5. Use **Abrir guia** para acessar o caso. Todo o conteúdo aparece em uma única página, em sequência: dados da guia, triagem TUSS × Rol, documentos, situação documental, apoio decisório, pareceres, revisões e histórico das execuções.
6. O médico auditor pode acrescentar PDFs ou imagens fictícias e colar um print com `Ctrl+V`. Esses arquivos apoiam o parecer, mas não substituem o pedido médico com indicação e justificativa nem o laudo anatomopatológico. A análise da DUT 60 só é liberada quando os documentos obrigatórios estiverem presentes.
7. Clique em **Gerar parecer**. A resposta pode levar alguns minutos. Ao concluir, a página posiciona o navegador diretamente no parecer sem esconder as outras seções. Leia a seção A e a minuta da seção B, confronte a fonte, o item da DUT, as evidências e as lacunas. Registre como divergência qualquer resultado inadequado.
8. Na seção de revisão médica, informe a conformidade, a concordância ou divergência e a observação ou conduta do médico auditor. Cada análise mantém somente uma revisão médica atual: um novo envio atualiza a revisão existente, sem duplicá-la no histórico.
9. Ao registrar a revisão médica de um parecer, o caso é encaminhado para a fila gerencial e o navegador abre **Discutir caso com gerência**. Nessa tela é possível consultar análise, revisão, histórico e gerar o PDF consolidado com os anexos sintéticos. A emissão do pacote não envia mensagens nem encerra a guia.
10. Use **Finalizar caso** para retirar o caso da fila ativa. A finalização não apaga o caso, as execuções, as revisões nem a trilha de auditoria. A integração transacional com uma operadora real continua dependendo de API e autorização institucional.

## Linux em EC2 (acesso por túnel SSH)

O serviço permanece vinculado a `127.0.0.1`; não abra a porta da aplicação para a internet. A Beta não está preparada para exposição pública. Use somente os casos sintéticos e uma instância/volume persistente autorizado.

1. Instale Python 3.10+ e suporte a `venv` na distribuição Linux da instância. Na raiz do projeto, crie o ambiente e instale as dependências:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install -r mvp/requirements.txt
   ```

2. Crie ou edite `.env` na raiz do projeto, defina `GEMINI_API_KEY` sem incluí-la em comandos ou logs e restrinja o arquivo ao usuário do serviço:

   ```bash
   chmod 600 .env
   ```

   No primeiro início, a aplicação grava `AUDITIA_JWT_SECRET` nesse arquivo; por isso, ele precisa ser gravável por esse usuário e ficar em armazenamento persistente.
3. Inicie a Beta a partir de qualquer diretório:

   ```bash
   bash mvp/iniciar_beta.sh
   ```

   O serviço usa a porta `5000`. Mantenha o processo ativo; `Ctrl+C` o encerra.
4. No Security Group da EC2, permita SSH (`22`) somente a partir do seu IP; não crie regra de entrada para `5000`. No seu computador, abra um túnel SSH (ajuste usuário, endereço e chave para sua instância):

   ```bash
   ssh -N -L 5000:127.0.0.1:5000 -i caminho-da-chave.pem ec2-user@ENDERECO-DA-EC2
   ```

   Em outra janela do computador, acesse http://127.0.0.1:5000. Para Ubuntu, o usuário SSH costuma ser `ubuntu`; confirme o usuário da imagem EC2 utilizada.

O launcher usa `.venv` se existir e, caso contrário, procura `python3` no `PATH`. O aplicativo usa `mvp/auditia-beta.sqlite3`; não substitua bancos existentes nem use dados reais. Para OCR de imagens/PDFs digitalizados, instale Tesseract e o idioma português separadamente.

### Validação básica sem chamadas à IA

Para validar login e dados já existentes na base de demonstração, sem executar análises nem instalar as dependências opcionais de PDF/OCR:

1. Na raiz do projeto, instale os requisitos mínimos:

   ```bash
   .venv/bin/python -m pip install -r mvp/requirements-validacao.txt
   ```

2. Inicie o modo de validação:

   ```bash
   bash mvp/iniciar_validacao.sh
   ```

   Esse modo usa `mvp/auditia-governanca-demo.sqlite3`, mantém o servidor em `127.0.0.1:5000` e bloqueia os envios para análise. Não precisa de `GEMINI_API_KEY`; pareceres existentes podem ser consultados. Preserve o `.env` existente e permita que o usuário do serviço o leia e grave nele o segredo JWT. Em EC2, use o túnel SSH descrito acima; não exponha a porta `5000`. A inicialização pode atualizar o esquema, e o login, o aceite do termo e os eventos de auditoria podem gravar no banco. Use as credenciais já cadastradas; não compartilhe senhas ou o arquivo `.env`.

   Para validar o modo sem as dependências opcionais de PDF/OCR:

   ```bash
   .venv/bin/python -B -m unittest discover -s mvp/tests -p test_validacao_basica.py -v
   ```

## Estados do caso

- **Ativo:** aparece na tela Casos e pode receber análise e revisão.
- **Gerência:** foi encaminhado automaticamente após o registro da revisão médica do parecer e aparece na fila de discussão gerencial.
- **Finalizado:** deixa de aparecer na fila ativa, mas mantém o histórico e os registros de auditoria.

Os botões de encaminhamento e finalização respeitam a operadora da sessão, autenticação e proteção CSRF. A interface usa alertas de sucesso, erro e processamento para confirmar as ações.
## Escopo de verificação
Parecer sempre preliminar. A aplicação não mede confiança probabilística calibrada. Nenhuma saída tem validação clínica formal. Sem modelo disponível, a aplicação sinaliza falha e preserva o caso. Para fotos (JPEG, PNG, WebP), prints e PDFs digitalizados, instale Tesseract OCR com o idioma português (`por.traineddata`); confira com `tesseract --list-langs`. O aplicativo procura o executável no `PATH` ou na pasta padrão do Windows. No caso, cole o print com `Ctrl+V` ou selecione o arquivo e clique em **Gerar parecer**. A leitura ocorre por página, localmente. Revise a transcrição preservada nas entradas da execução, especialmente negações, medidas e unidades. Os arquivos são lidos localmente; o histórico conserva texto e hash, não o binário. A fonte regulatória é a cópia fornecida no projeto, sem atualização automática.
