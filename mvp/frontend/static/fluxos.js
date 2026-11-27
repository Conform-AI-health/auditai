const aceite = document.querySelector('input[name="aceite"]');
if (aceite) {
    const botao = aceite.form.querySelector('button[type="submit"]');
    botao.disabled = !aceite.checked;
    aceite.addEventListener('change', () => { botao.disabled = !aceite.checked; });
}

let carregando = false;
document.addEventListener('click', async event => {
    const link = event.target.closest('#proxima');
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    if (carregando) return;
    carregando = true;
    const estado = document.querySelector('#estado');
    estado.textContent = 'Carregando eventos…';
    try {
        const resposta = await fetch(link.href);
        if (resposta.redirected) {
            location.assign(resposta.url);
            return;
        }
        if (!resposta.ok) throw new Error();
        const pagina = new DOMParser().parseFromString(await resposta.text(), 'text/html');
        document.querySelector('main').replaceWith(pagina.querySelector('main'));
        history.pushState({}, '', link.href);
    } catch {
        estado.textContent = 'Erro ao carregar os eventos. Tente novamente.';
    } finally {
        carregando = false;
    }
});
window.addEventListener('popstate', () => location.reload());

document.querySelectorAll('textarea[name="note"]').forEach(campo => {
    const contador = campo.parentElement.querySelector('output');
    campo.addEventListener('input', () => {
        contador.textContent = campo.value.length + ' / ' + campo.maxLength;
    });
});
