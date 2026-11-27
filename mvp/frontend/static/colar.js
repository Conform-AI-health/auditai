document.addEventListener("paste", (event) => {
  const input = document.querySelector('input[name="anexo"]');
  const images = Array.from(event.clipboardData?.files || []).filter(f => f.type.startsWith("image/"));
  if (!input || !images.length) return;
  event.preventDefault();
  const transfer = new DataTransfer();
  for (const file of [...input.files, ...images]) transfer.items.add(file);
  input.files = transfer.files;
  document.querySelector("#anexos-status").textContent = transfer.files.length + " anexo(s) selecionado(s).";
});
