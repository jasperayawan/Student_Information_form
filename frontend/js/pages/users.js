const ROLE_LABELS = {
    admin: "Administrator",
    college_admin: "IT Administrator",
    instructor: "Instructor",
    student: "Student",
}

Pages.push({
    id: "users",
    nav: "Users & Roles",
    title: "User and Role Management",
    visible: () => Auth.can("users.manage"),

    async render(el) {
        const instructors = (await api("/instructors/")).data
        el.innerHTML = `<p class="muted">Student and instructor accounts must be linked to their record.
            IT administrators have read-only access to all records and reports.</p>
            <div class="page-actions"><button type="button" class="btn btn-primary" data-add>Create account</button></div>
            <div data-list></div>`

        const list = UI.listView(el.querySelector("[data-list]"), {
            search: { placeholder: "Search username or name…",
                      text: r => `${r.username} ${r.student_name || ""} ${r.instructor_name || ""} ${r.student_number || ""}` },
            filters: [{ label: "All roles", options: Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label })),
                        match: (r, v) => r.role === v }],
            columns: [
                { label: "Username", value: r => r.username },
                { label: "Role", value: r => ROLE_LABELS[r.role] },
                { label: "Linked record", value: r => r.student_name ? `${r.student_name} (${r.student_number})`
                    : r.instructor_name ? `${r.instructor_name} (${r.instructor_number})` : "" },
                { label: "Status", html: r => r.is_active ? UI.badge("Active") : UI.badge("Disabled", "muted") },
            ],
            actions: r => UI.button("edit", r.id, "Edit", "edit") +
                (r.id === Auth.user.id ? "" : UI.button("delete", r.id, "Delete", "danger")),
            onAction: async (action, row) => {
                if (action === "edit") openForm(row)
                if (action === "delete") {
                    const ok = await UI.confirmAction(`Delete the account ${row.username}? The person will no longer be able to log in.`)
                    if (ok && await UI.run(() => api(`/users/${row.id}`, { method: "DELETE" }))) load()
                }
            },
        })

        const openForm = account => UI.formDialog({
            title: account ? `Edit ${account.username}` : "Create Account",
            fields: [
                account
                    ? { name: "username", label: "Username", display: true }
                    : { name: "username", label: "Username", required: true, minlength: 3, maxlength: 100,
                        pattern: "[A-Za-z0-9_.@\\-]+", autocomplete: "off" },
                { name: "password", label: account ? "New password (leave blank to keep)" : "Password", type: "password",
                  required: !account, minlength: 8, autocomplete: "new-password" },
                { name: "role", label: "Role", type: "select", required: true,
                  options: Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label })) },
                { name: "student_number", label: "Student ID (for student accounts)", pattern: "[0-9]{4}-[0-9]{4}",
                  placeholder: "e.g. 2026-0101" },
                { name: "instructor_id", label: "Instructor (for instructor accounts)", type: "select", numeric: true,
                  blank: "None", options: UI.options(instructors, "id", i => `${i.name} (${i.instructor_number})`) },
                ...(account ? [{ name: "is_active", label: "Account active", type: "checkbox", full: true }] : []),
            ],
            values: account || {},
            afterRender(form) {
                const sync = () => {
                    const role = form.elements.role.value
                    form.elements.student_number.closest(".field").hidden = role !== "student"
                    form.elements.instructor_id.closest(".field").hidden = role !== "instructor"
                    form.elements.student_number.required = role === "student"
                    form.elements.instructor_id.required = role === "instructor"
                }
                form.elements.role.addEventListener("change", sync)
                sync()
            },
            async onSubmit(data) {
                const body = { role: data.role, student_id: null, instructor_id: null }
                if (data.role === "student") body.student_id = await findStudentId(data.student_number)
                if (data.role === "instructor") body.instructor_id = data.instructor_id
                if (data.password) body.password = data.password
                let res
                if (account) {
                    body.is_active = data.is_active
                    res = await api(`/users/${account.id}`, { method: "PUT", body })
                } else {
                    body.username = data.username
                    res = await api("/users/", { method: "POST", body })
                }
                UI.toast(res.message)
                load()
            },
        })

        async function findStudentId(number) {
            const { data } = await api("/students/", { query: { q: number, page_size: 5 } })
            const match = data.find(s => s.student_number === number)
            if (!match) throw new Error(`No student has the ID ${number}.`)
            return match.id
        }

        async function load() {
            list.setRows((await api("/users/")).data)
        }

        el.querySelector("[data-add]").addEventListener("click", () => openForm(null))
        await load()
    },
})
