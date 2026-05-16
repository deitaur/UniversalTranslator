document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('demoButton');
    const messageElement = document.getElementById('message');

    if (button) {
        button.addEventListener('click', () => {
            // Simple function demonstrating basic JavaScript functionality
            console.log('Button clicked! Basic JS interactivity working.');
            messageElement.textContent = 'Success! The button was clicked and the script executed.';
        });
    }
});