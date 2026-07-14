(function () {
  var form = document.getElementById("coach-form");
  var out = document.getElementById("coach-response");
  if (!form) { return; }
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    out.textContent = "";
    var data = new FormData(form);
    fetch("/coach/ask", { method: "POST", body: data }).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (text) { out.textContent = text; });
      }
      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      function pump() {
        return reader.read().then(function (result) {
          if (result.done) { return; }
          out.textContent += decoder.decode(result.value, { stream: true });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      out.textContent = "Request failed: " + err;
    });
  });
})();
