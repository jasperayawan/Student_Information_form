const SECTION_COLUMNS = [
    { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
    { label: "Section", value: r => r.section_code },
    { label: "Days", value: r => UI.days(r.pattern) },
    { label: "Time", value: r => UI.timeRange(r) },
    { label: "Room", value: r => r.room_code || "TBA" },
    { label: "Slots", html: r => UI.seats(r) },
]

function instructorSchedule(instructor) {
    const subjects = [...new Set(instructor.sections.map(s => `${s.subject_code} — ${s.subject_title}`))]
    return UI.details([
        ["Instructor ID", instructor.instructor_number], ["Email", instructor.email],
        ["Contact number", instructor.contact_number], ["Department", instructor.department],
        ["Assigned subjects", subjects.join("; ") || "None yet"],
    ]) + "<h3>Teaching schedule and classrooms</h3>" +
        (instructor.sections.length ? UI.table(SECTION_COLUMNS, instructor.sections) + UI.weekGrid(instructor.sections)
            : UI.empty("No classes assigned yet."))
}

Pages.push({
    id: "instructors",
    nav: "Instructors",
    title: "Instructor Management",
    visible: () => Auth.can("instructors.view"),

    async render(el) {
        const canManage = Auth.can("instructors.manage")
        const departments = (await api("/instructors/departments")).data
        el.innerHTML = `<div class="page-actions">${canManage ? '<button type="button" class="btn btn-primary" data-add>Register instructor</button>' : ""}</div><div data-list></div>`

        const fields = [
            { name: "instructor_number", label: "Instructor ID", display: true, help: "Generated automatically by the system." },
            { name: "name", label: "Full name", required: true, minlength: 2, maxlength: 120 },
            { name: "email", label: "Email address", type: "email", required: true },
            { name: "contact_number", label: "Contact number", type: "tel", required: true, pattern: "\\+?[0-9]{7,15}" },
            { name: "department", label: "Department", type: "select", required: true, blank: "Choose a department…",
              options: departments },
            { name: "is_active", label: "Active (available for class assignments)", type: "checkbox", full: true },
        ]

        const list = UI.listView(el.querySelector("[data-list]"), {
            search: { placeholder: "Search by name, ID, email or department…",
                      text: r => `${r.name} ${r.instructor_number} ${r.email} ${r.department}` },
            filters: [{ label: "All departments", options: departments, match: (r, v) => r.department === v },
                      { label: "Any status", options: [{ value: "1", label: "Active" }, { value: "0", label: "Inactive" }],
                        match: (r, v) => String(r.is_active) === v }],
            columns: [
                { label: "Instructor ID", value: r => r.instructor_number },
                { label: "Name", value: r => r.name },
                { label: "Email", value: r => r.email },
                { label: "Contact", value: r => r.contact_number },
                { label: "Department", value: r => r.department },
                { label: "Classes", value: r => r.section_count, num: true },
                { label: "Status", html: r => r.is_active ? UI.badge("Active") : UI.badge("Inactive", "muted") },
            ],
            actions: r => UI.button("view", r.id, "Schedule") +
                (canManage ? UI.button("edit", r.id, "Edit", "edit") + UI.button("delete", r.id, "Delete", "danger") : ""),
            emptyText: "No instructors registered yet.",
            onAction: async (action, row) => {
                if (action === "view") {
                    const dialog = UI.openDialog({ title: row.name, body: UI.loading(), wide: true })
                    try {
                        dialog.body.innerHTML = instructorSchedule((await api(`/instructors/${row.id}`)).data)
                    } catch (err) {
                        dialog.body.innerHTML = UI.errorState(err.message)
                    }
                }
                if (action === "edit") openForm(row)
                if (action === "delete") {
                    const ok = await UI.confirmAction(`Delete instructor ${row.name}? This cannot be undone.`)
                    if (ok && await UI.run(() => api(`/instructors/${row.id}`, { method: "DELETE" }))) load()
                }
            },
        })

        const openForm = instructor => UI.formDialog({
            title: instructor ? "Edit Instructor" : "Register Instructor",
            fields: fields.filter(f => instructor || f.name !== "instructor_number"),
            values: instructor || { is_active: true },
            async onSubmit(body) {
                const res = instructor
                    ? await api(`/instructors/${instructor.id}`, { method: "PUT", body })
                    : await api("/instructors/", { method: "POST", body })
                UI.toast(res.message)
                load()
            },
        })

        async function load() {
            try {
                list.setRows((await api("/instructors/")).data)
            } catch (err) {
                UI.toast(err.message, "error")
            }
        }

        el.querySelector("[data-add]")?.addEventListener("click", () => openForm(null))
        await load()
    },
})

Pages.push({
    id: "teaching",
    nav: "My Classes",
    title: "My Classes",
    visible: () => Auth.can("self.teaching"),

    async render(el) {
        let me
        try {
            me = (await api("/instructors/me")).data
        } catch (err) {
            el.innerHTML = UI.empty(err.message)
            return
        }
        el.innerHTML = `<section class="panel">${instructorSchedule(me)}</section>
            <section class="panel"><h2>Class rosters</h2><div data-rosters></div></section>`
        const target = el.querySelector("[data-rosters]")
        target.innerHTML = me.sections.length
            ? UI.table(SECTION_COLUMNS, me.sections, r => UI.button("roster", r.id, "View roster"))
            : UI.empty("No classes assigned yet.")
        target.addEventListener("click", e => {
            const btn = e.target.closest("[data-action=roster]")
            if (btn) showRoster(btn.dataset.id)
        })
    },
})

async function showRoster(sectionId, { onDrop } = {}) {
    const dialog = UI.openDialog({ title: "Class roster", body: UI.loading(), wide: true })
    try {
        const { data } = await api(`/sections/${sectionId}/roster`)
        dialog.body.innerHTML = `<p><strong>${UI.esc(data.subject_code)} — ${UI.esc(data.subject_title)}</strong>,
            section ${UI.esc(data.section_code)} · ${UI.esc(UI.slotText(data))} · Room ${UI.esc(data.room_code || "TBA")}
            · Instructor ${UI.esc(data.instructor_name || "TBA")}</p><p>${UI.seats(data)}</p>` +
            (data.students.length ? UI.table([
                { label: "Student ID", value: r => r.student_number },
                { label: "Name", value: r => r.name },
                { label: "Email", value: r => r.email || "" },
                { label: "Enrolled", value: r => r.enrolled_at },
            ], data.students, onDrop ? r => UI.button("drop", r.enrollment_id, "Drop", "danger") : null)
                : UI.empty("No students enrolled yet."))
        if (onDrop) {
            dialog.body.addEventListener("click", async e => {
                const btn = e.target.closest("[data-action=drop]")
                if (!btn) return
                const student = data.students.find(s => String(s.enrollment_id) === btn.dataset.id)
                if (await UI.confirmAction(`Drop ${student.name} from this class?`, { confirmText: "Drop" })) {
                    if (await UI.run(() => api(`/enrollments/${student.enrollment_id}`, { method: "DELETE" }))) {
                        dialog.close()
                        onDrop()
                    }
                }
            })
        }
    } catch (err) {
        dialog.body.innerHTML = UI.errorState(err.message)
    }
    return dialog
}
