// Confirm destructive actions. Usage: <form data-confirm="Are you sure?">
document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});

// Language switcher: switch as soon as another language is picked.
document.addEventListener("change", function (event) {
    var form = event.target.form;
    if (form && form.hasAttribute("data-autosubmit")) {
        form.submit();
    }
});
