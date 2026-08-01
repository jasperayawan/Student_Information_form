const API = "http://127.0.0.1:8000"

document.addEventListener('DOMContentLoaded', () => {
    const tbody = document.getElementById("studentInfo");
    const studentForm = document.getElementById("form")
    const searchInput = document.getElementById("searchInput")
    const modal = document.getElementById("modal")
    const close_btn = document.getElementById("close-btn")
    const editStudentForm = document.getElementById("editStudentForm")

    let allStudents = []

    loadStudentsInfo()


    async function loadStudentsInfo() {
        const response = await fetch(`${API}/students`);

        const students = await response.json();
        allStudents = students?.data || []

        renderTable(allStudents)
    }

    function renderTable(students) {
        let html = ""
        students.forEach(student => {
            html += `
            <tr>
                <td>${student.id}</td>
                <td>${student.name}</td>
                <td>${student.age}</td>
                <td>${student.course}</td>
                <td>${student.birth_date}</td>
                <td>${student.address}</td>
                <td>${student.contact_number}</td>
                <td class="edit-btn" data-id="${student.id}">Edit</td>
                <td class="delete-btn" data-id="${student.id}">Delete</td>
            </tr>
        `
        })

        tbody.innerHTML = html

        const editBtn = tbody.querySelectorAll(".edit-btn")
        editBtn.forEach(button => {
            button.addEventListener('click', (e) => {
                const studentId = e.target.getAttribute("data-id")

                const student = students.find(s => s.id == studentId)

                if (studentId) {
                    document.getElementById('edit-id').value = student.id
                    document.getElementById('edit-name').value = student.name
                    document.getElementById('edit-age').value = student.age
                    document.getElementById('edit-course').value = student.course
                    document.getElementById('edit-birth-date').value = student.birth_date
                    document.getElementById('edit-address').value = student.address
                    document.getElementById('edit-contact-number').value = student.contact_number
                }
                modal.style.display = "flex"
            })
        })
    }

    close_btn.addEventListener('click', (e) => {
        modal.style.display = "none"
    })


    tbody.addEventListener('click', async (e) => {
        if (e.target.classList.contains("delete-btn")) {
            const id = e.target.getAttribute('data-id')

            try {
                const response = await fetch(`${API}/students/${id}`, {
                    method: "DELETE",
                })

                const result = await response.json();
                alert(result.message)
                await loadStudentsInfo();
            } catch (err) {
                console.log(err)
            }
        }
    })


    studentForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const formData = new FormData(studentForm);
        const body = Object.fromEntries(formData)
        console.log(body)

        if (!body.name || !body.age || !body.course || !body.birth_date || !body.address || !body.contact_number) {
            alert("Fill in the required field")
            return;
        }

        try {
            const res = await fetch(`${API}/students`, {
                method: 'POST',
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            });
            if (res.ok) {
                const result = await res.json();
                alert(result.message)
                studentForm.reset();
                await loadStudentsInfo()
            }
        }
        catch (err) {
            console.log(err)
        }
    })


    editStudentForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData(editStudentForm);
        const body = Object.fromEntries(formData)
        const id = document.getElementById('edit-id').value

        try {
            const res = await fetch(`${API}/students/${id}`, {
                method: 'PUT',
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            })
            if (res.ok) {
                const result = await res.json();
                alert(result.message)
                modal.style.display = "none"
                await loadStudentsInfo()
            }
        } catch (err) {
            console.log(err)
        }
    })


    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim()

        const filteredStudent = allStudents.filter(student => {
            const name = student.name ? student.name.toLowerCase() || student.name.toUpperCase() : ""
            const course = student.course ? student.course.toLowerCase() || student.course.toUpperCase() : ""
            const address = student.address ? student.address.toLowerCase() || student.address.toUpperCase() : ""

            return name.includes(query) || course.includes(query) || address.includes(query)
        })

        renderTable(filteredStudent)
    })
})
