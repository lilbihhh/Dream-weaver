(function () {
  var form = document.getElementById("coach-form");
  var out = document.getElementById("coach-response");
  var submit = form ? form.querySelector("button[type='submit']") : null;
  if (!form) { return; }
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    out.textContent = "Connecting to Grok…";
    out.classList.add("streaming");
    if (submit) { submit.disabled = true; }
    var data = new FormData(form);
    fetch("/coach/ask", { method: "POST", body: data }).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (text) { out.textContent = text; });
      }
      out.textContent = "";
      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      function pump() {
        return reader.read().then(function (result) {
          if (result.done) {
            out.textContent += decoder.decode();
            return;
          }
          out.textContent += decoder.decode(result.value, { stream: true });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      out.textContent = "Request failed: " + err;
    }).finally(function () {
      out.classList.remove("streaming");
      if (submit) { submit.disabled = false; }
    });
  });
})();
