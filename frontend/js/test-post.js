const startBtn = document.querySelector('.btn-primary');
function handleStartClick() {
    const payload = {
        message: "Hello, this is a test payload!",
        timestamp: new Date().toISOString()
    };
    const url = '/api/test'; // API endpoint

    const response  = fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(data => {
        console.log('Server response:', data);
        const outputDiv = document.getElementById('output');
        if (outputDiv) {
            outputDiv.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        }
    })
    .catch(error => {
        console.error('Error:', error);
    })
}

if (startBtn) {
    startBtn.addEventListener('click', handleStartClick);
}