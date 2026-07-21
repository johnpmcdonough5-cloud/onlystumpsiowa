/* Sends the quote form to a GoHighLevel workflow via its Inbound Webhook URL. */
(function () {
  // Paste your GHL Inbound Webhook URL here (Automation > Workflows > Inbound Webhook trigger).
  var GHL_WEBHOOK_URL = "https://services.leadconnectorhq.com/hooks/Gvvmfiz9m5qveMekUyjZ/webhook-trigger/8d34682b-095f-43ba-b815-8adba8d50337";

  var form = document.querySelector("form.quote-form");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    if (GHL_WEBHOOK_URL.indexOf("http") !== 0) {
      alert("This form isn't connected yet. Please call us at (563) 500-2980.");
      return;
    }

    var btn = form.querySelector('button[type="submit"]');
    var data = {
      name: form.querySelector("#name").value.trim(),
      phone: form.querySelector("#phone").value.trim(),
      email: form.querySelector("#email").value.trim(),
      county: form.querySelector("#county") ? form.querySelector("#county").value : "",
      bulk_estimate: (form.querySelector('input[name="bulk"]:checked') || {}).value || "No",
      message: form.querySelector("#message") ? form.querySelector("#message").value.trim() : "",
      page: window.location.pathname,
      source: "OnlyStumps website quote form"
    };

    btn.disabled = true;
    btn.textContent = "Sending…";

    fetch(GHL_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        showSuccess();
      })
      .catch(function () {
        // Retry opaque in case of a CORS preflight issue; GHL still receives the payload.
        fetch(GHL_WEBHOOK_URL, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "text/plain" },
          body: JSON.stringify(data)
        })
          .then(showSuccess)
          .catch(function () {
            btn.disabled = false;
            btn.textContent = "Send my request";
            alert("Something went wrong sending your request. Please call us at (563) 500-2980.");
          });
      });

    function showSuccess() {
      var body = form.querySelector(".form-body");
      body.innerHTML =
        '<div style="text-align:center;padding:2rem 1rem">' +
        '<div style="font-size:2.5rem;line-height:1">✅</div>' +
        "<h3 style=\"margin:.75rem 0 .5rem\">Request received!</h3>" +
        "<p>Thanks, " + escapeHtml(data.name.split(" ")[0] || "friend") + ". We'll follow up with your free quote — usually the same day.</p>" +
        '<p style="margin-top:.75rem">Need us sooner? Call <a href="tel:5635002980"><strong>(563) 500-2980</strong></a>.</p>' +
        "</div>";
    }

    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    }
  });
})();
