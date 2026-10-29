
const form = document.querySelector("form");
const resumeInput = document.querySelector("#resume");

form.addEventListener("submit", (event) => {
    if (!resumeInput.files.length) {
        event.preventDefault();
        alert("Please select your resume PDF.");
        return;
    }

    if (resumeInput.files[0].size > 5 * 1024 * 1024) {
        event.preventDefault();
        alert("PDF must be 5 MB or smaller.");
    }
});
