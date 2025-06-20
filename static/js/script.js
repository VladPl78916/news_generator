document.addEventListener('DOMContentLoaded', function() {
    const quill = new Quill('#editor', {
        modules: {
            toolbar: [
                [{ 'header': [1, 2, false] }],
                ['bold', 'italic', 'underline'],
                [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                ['link', 'image'],
                ['clean']
            ]
        },
        theme: 'snow'
    });

    const form = document.getElementById('newsForm');
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        document.getElementById('content').value = quill.root.innerHTML;
        
        const formData = new FormData(form);
        
        try {
            const response = await fetch('/publish', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok) {
                alert(result.success);
                form.reset();
                quill.root.innerHTML = '';
            } else {
                throw new Error(result.error || 'Ошибка сервера');
            }
        } catch (error) {
            alert(`Ошибка: ${error.message}`);
        }
    });
});