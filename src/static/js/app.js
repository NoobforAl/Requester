// Confirm destructive actions. Usage: <form data-confirm="Are you sure?">
document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});
