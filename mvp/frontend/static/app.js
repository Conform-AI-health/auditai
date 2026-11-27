(() => {
  const container = document.querySelector("#alertas");

  function showAlert(message, type = "success", duration = 5000, processing = false) {
    if (!container || !message) return;
    container.innerHTML = "";
    const element = document.createElement("div");
    element.className = `alert alert-${type} fade show shadow-sm d-flex align-items-center gap-2`;
    element.setAttribute("role", processing ? "status" : "alert");
    if (processing) {
      const spinner = document.createElement("span");
      spinner.className = "spinner-border spinner-border-sm";
      spinner.setAttribute("aria-hidden", "true");
      element.append(spinner);
    }
    const text = document.createElement("span");
    text.className = "flex-grow-1";
    text.textContent = message;
    element.append(text);
    if (!processing) {
      element.classList.add("alert-dismissible");
      const close = document.createElement("button");
      close.type = "button";
      close.className = "btn-close";
      close.dataset.bsDismiss = "alert";
      close.setAttribute("aria-label", "Fechar mensagem");
      element.append(close);
    }
    container.append(element);
    if (duration > 0) {
      window.setTimeout(() => {
        if (!element.isConnected) return;
        if (window.bootstrap?.Alert) {
          window.bootstrap.Alert.getOrCreateInstance(element).close();
        } else {
          element.remove();
        }
      }, duration);
    }
    return element;
  }

  const saved = sessionStorage.getItem("auditia-alert");
  if (saved) {
    sessionStorage.removeItem("auditia-alert");
    try {
      const data = JSON.parse(saved);
      showAlert(data.message, data.type);
    } catch (_) {
      sessionStorage.removeItem("auditia-alert");
    }
  }

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "post") return;
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    showAlert("Processando…", "info", 0, true);

    try {
      const url = new URL(form.action, window.location.href);
      url.pathname = `/api${url.pathname}`;
      const fields = new FormData(form);
      const multipart = [...fields.values()].some((value) => value instanceof File && value.size > 0);
      const response = await fetch(url, {
        method: "POST",
        body: multipart ? fields : new URLSearchParams(fields),
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      });
      const disposition = response.headers.get("Content-Disposition") || "";
      const type = response.headers.get("Content-Type") || "";
      if (disposition || type.includes("application/pdf") || type.includes("text/csv")) {
        if (!response.ok) throw new Error("Não foi possível gerar o arquivo.");
        const blob = await response.blob();
        const download = document.createElement("a");
        download.href = URL.createObjectURL(blob);
        const match = disposition.match(/filename="?([^";]+)"?/i);
        download.download = match ? match[1] : "auditia-arquivo";
        download.click();
        URL.revokeObjectURL(download.href);
        showAlert("Arquivo gerado com sucesso.");
        return;
      }
      const data = await response.json();
      if (!response.ok || !data.ok) {
        if (response.status === 422 && data.redirect) {
          sessionStorage.setItem("auditia-alert", JSON.stringify({ message: data.message, type: "danger" }));
          window.location.assign(data.redirect);
          return;
        }
        throw new Error(data.message || "Não foi possível concluir a operação.");
      }
      if (data.redirect) {
        sessionStorage.setItem("auditia-alert", JSON.stringify({ message: data.message, type: "success" }));
        window.location.assign(data.redirect);
      } else {
        showAlert(data.message);
      }
    } catch (error) {
      showAlert(error.message || "Falha de comunicação com o servidor.", "danger");
    } finally {
      if (button) button.disabled = false;
    }
  });
})();
