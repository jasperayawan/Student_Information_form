const YEAR_LEVELS = [1, 2, 3, 4, 5, 6].map(n => ({ value: n, label: `Year ${n}` }))

function studentFields(courses) {
    const personal = "Personal Background"
    const education = "Educational Background"
    return [
        { name: "student_number", label: "Student ID", section: personal, display: true,
          help: "Generated automatically: registration year + 4 random digits." },
        { name: "name", label: "Full name", section: personal, required: true, minlength: 2, maxlength: 120 },
        { name: "birth_date", label: "Date of birth", section: personal, type: "date", required: true,
          max: new Date().toISOString().slice(0, 10) },
        { name: "age", label: "Age", section: personal, type: "number", required: true, min: 5, max: 120 },
        { name: "sex", label: "Sex", section: personal, type: "select", required: true,
          options: [{ value: "Male", label: "Male" }, { value: "Female", label: "Female" }] },
        { name: "contact_number", label: "Contact number", section: personal, type: "tel", required: true,
          pattern: "\\+?[0-9]{7,15}", placeholder: "09171234567" },
        { name: "email", label: "Email address", section: personal, type: "email", required: true, maxlength: 254 },
        { name: "address", label: "Address", section: personal, required: true, full: true, maxlength: 255 },
        { name: "previous_school", label: "Previous school", section: education, required: true, maxlength: 200 },
        { name: "previous_attainment", label: "Previous educational attainment", section: education,
          required: true, maxlength: 120, placeholder: "e.g. Senior High School Graduate" },
        { name: "course_id", label: "Selected course", section: education, type: "select", required: true,
          numeric: true, options: UI.options(courses, "id", c => `${c.code} — ${c.name}`) },
        { name: "year_level", label: "Year level", section: education, type: "select", numeric: true,
          blank: "Not applicable", options: YEAR_LEVELS },
    ]
}

function studentDetails(s) {
    return `<h3>Personal Background</h3>${UI.details([
        ["Student ID", s.student_number], ["Full name", s.name], ["Date of birth", s.birth_date],
        ["Age", s.age], ["Sex", s.sex], ["Address", s.address], ["Contact number", s.contact_number],
        ["Email", s.email],
    ])}<h3>Educational Background</h3>${UI.details([
        ["Previous school", s.previous_school], ["Previous attainment", s.previous_attainment],
        ["Course", `${s.course} — ${s.course_name}`], ["Year level", s.year_level ? `Year ${s.year_level}` : ""],
    ])}`
}

Pages.push({
    id: "students",
    nav: "Students",
    title: "Student Management",
    visible: () => Auth.can("students.view"),

    async render(el) {
        const courses = (await api("/courses/")).data
        const canManage = Auth.can("students.manage")
        const state = { q: "", course_id: "", page: 1, page_size: 10 }

        el.innerHTML = `
            <div class="page-actions">
                ${canManage ? '<button type="button" class="btn btn-primary" data-add>Register student</button>' : ""}
            </div>
            <div class="list-tools">
                <input type="search" class="search" id="searchInput" placeholder="Search by name, ID, email, address or course…" aria-label="Search students">
                <select data-course aria-label="Filter by course"><option value="">All courses</option>
                    ${courses.map(c => `<option value="${c.id}">${UI.esc(c.code)}</option>`).join("")}</select>
            </div>
            <div data-table>${UI.loading()}</div>
            <div class="pager" data-pager></div>`

        const tableEl = el.querySelector("[data-table]")
        const pagerEl = el.querySelector("[data-pager]")
        let rows = []

        async function load() {
            tableEl.innerHTML = UI.loading()
            try {
                const res = await api("/students/", { query: state })
                rows = res.data
                tableEl.innerHTML = rows.length ? UI.table([
                    { label: "Student ID", value: r => r.student_number },
                    { label: "Name", value: r => r.name },
                    { label: "Sex", value: r => r.sex },
                    { label: "Course", value: r => r.course },
                    { label: "Year", value: r => r.year_level || "", num: true },
                    { label: "Contact", value: r => r.contact_number },
                    { label: "Email", html: r => r.email ? UI.esc(r.email) : UI.badge("Incomplete record", "warn") },
                ], rows, r => UI.button("view", r.id, "View") +
                    (canManage ? UI.button("edit", r.id, "Edit", "edit") + UI.button("delete", r.id, "Delete", "danger") : ""),
                { pageSize: Infinity })
                    : UI.empty(state.q || state.course_id ? "No students match your search." : "No students registered yet.")
                pagerEl.innerHTML = UI.pagerHtml(res.page, res.page_size, res.total)
            } catch (err) {
                tableEl.innerHTML = UI.errorState(err.message)
                pagerEl.innerHTML = ""
            }
        }

        let timer
        el.querySelector("#searchInput").addEventListener("input", e => {
            clearTimeout(timer)
            timer = setTimeout(() => { state.q = e.target.value.trim(); state.page = 1; load() }, 300)
        })
        el.querySelector("[data-course]").addEventListener("change", e => { state.course_id = e.target.value; state.page = 1; load() })
        pagerEl.addEventListener("click", e => {
            const btn = e.target.closest("[data-page]")
            if (btn) { state.page = Number(btn.dataset.page); load() }
        })

        const openForm = student => UI.formDialog({
            title: student ? "Edit Student" : "Register Student",
            wide: true,
            fields: studentFields(courses).filter(f => student || f.name !== "student_number"),
            values: student || {},
            submitText: student ? "Save Changes" : "Register",
            async onSubmit(body) {
                const res = student
                    ? await api(`/students/${student.id}`, { method: "PUT", body })
                    : await api("/students/", { method: "POST", body })
                UI.toast(res.message)
                await load()
            },
        })

        el.querySelector("[data-add]")?.addEventListener("click", () => openForm(null))

        tableEl.addEventListener("click", async e => {
            const btn = e.target.closest("[data-action]")
            if (!btn) return
            const student = rows.find(r => String(r.id) === btn.dataset.id)
            if (btn.dataset.action === "edit") openForm(student)
            if (btn.dataset.action === "view") {
                const dialog = UI.openDialog({ title: student.name, body: UI.loading(), wide: true })
                try {
                    const { data } = await api(`/students/${student.id}`)
                    dialog.body.innerHTML = studentDetails(data) + "<h3>Enrolled classes</h3>" + (data.enrollments.length
                        ? UI.table([
                            { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
                            { label: "Section", value: r => r.section_code },
                            { label: "Schedule", value: r => UI.slotText(r) },
                            { label: "Room", value: r => r.room_code || "TBA" },
                            { label: "Instructor", value: r => r.instructor_name || "TBA" },
                        ], data.enrollments)
                        : UI.empty("Not enrolled in any class yet."))
                } catch (err) {
                    dialog.body.innerHTML = UI.errorState(err.message)
                }
            }
            if (btn.dataset.action === "delete") {
                const ok = await UI.confirmAction(`Delete ${student.name} (${student.student_number})? This cannot be undone.`)
                if (ok && await UI.run(() => api(`/students/${student.id}`, { method: "DELETE" }))) load()
            }
        })

        load()
    },
})

Pages.push({
    id: "profile",
    nav: "My Profile",
    title: "My Profile",
    visible: () => Auth.can("self.profile"),

    async render(el) {
        let student
        try {
            student = (await api("/students/me")).data
        } catch (err) {
            el.innerHTML = UI.empty(err.message)
            return
        }
        el.innerHTML = `<section class="panel">
            <div class="page-actions"><button type="button" class="btn btn-primary" data-edit>Update contact details</button></div>
            ${studentDetails(student)}
            <p class="muted">To correct your name, birth date, course or other records, please contact the registrar.</p>
        </section>`
        const reload = () => this.render(el)
        el.querySelector("[data-edit]").addEventListener("click", () => UI.formDialog({
            title: "Update contact details",
            fields: [
                { name: "address", label: "Address", required: true, full: true, maxlength: 255 },
                { name: "contact_number", label: "Contact number", type: "tel", required: true, pattern: "\\+?[0-9]{7,15}" },
                { name: "email", label: "Email address", type: "email", required: true },
            ],
            values: student,
            async onSubmit(body) {
                const res = await api("/students/me", { method: "PUT", body })
                UI.toast(res.message)
                reload()
            },
        }))
    },
})
