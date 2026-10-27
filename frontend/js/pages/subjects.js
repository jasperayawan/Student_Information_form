Pages.push({
    id: "subjects",
    nav: "Subjects",
    title: "Subject Management",
    visible: () => Auth.can("subjects.view"),

    async render(el) {
        const isInstructor = Auth.user.role === "instructor"
        // Students see only the subjects they are enrolled in (filtered by the server).
        const isStudent = Auth.user.role === "student"
        // Instructors only see the subjects they teach, with counts for their own sections.
        const canSeeStudents = isInstructor || Auth.can("enrollments.view")
        const subjects = (await api("/subjects/")).data
        // Instructors have no Courses module, so the course filter comes from their subjects.
        const courses = Auth.can("courses.view")
            ? (await api("/courses/")).data
            : UI.coursesFrom(subjects)
        const canManage = Auth.can("subjects.manage")
        el.innerHTML = `<div class="page-actions">${canManage ? '<button type="button" class="btn btn-primary" data-add>Add subject</button>' : ""}</div><div data-list></div>`
        const list = UI.listView(el.querySelector("[data-list]"), {
            rows: subjects,
            search: { placeholder: "Search by code or descriptive title…", text: r => `${r.code} ${r.title}` },
            filters: [
                { label: "All courses", options: UI.options(courses, "id", c => c.code), match: (r, v) => String(r.course_id) === v },
                { label: "Any units", options: [{ value: "2", label: "2 units" }, { value: "3", label: "3 units" }],
                  match: (r, v) => String(r.units) === v },
            ],
            columns: [
                { label: "Code", value: r => r.code },
                { label: "Descriptive title", value: r => r.title },
                { label: "Course", value: r => r.course_code },
                { label: "Units", value: r => r.units, num: true },
                ...(isStudent ? [] : [
                    { label: isInstructor ? "My sections" : "Sections", value: r => r.section_count, num: true },
                    { label: "Enrolled students", value: r => r.enrolled_count, num: true },
                ]),
            ],
            actions: r => UI.button("view", r.id, isStudent ? "My class" : "Sections") +
                (canSeeStudents ? UI.button("students", r.id, "Students") : "") +
                (canManage ? UI.button("edit", r.id, "Edit", "edit") + UI.button("delete", r.id, "Delete", "danger") : ""),
            emptyText: isInstructor ? "You are not assigned to teach any subject yet."
                : isStudent ? "You are not enrolled in any subject yet. Enroll in classes on My Enrollment."
                : "No subjects yet.",
            onAction: async (action, row) => {
                if (action === "students") showSubjectStudents(row)
                if (action === "edit") openForm(row)
                if (action === "delete") {
                    const ok = await UI.confirmAction(`Delete subject ${row.code}? This cannot be undone.`)
                    if (ok && await UI.run(() => api(`/subjects/${row.id}`, { method: "DELETE" }))) load()
                }
                if (action === "view") {
                    const dialog = UI.openDialog({ title: `${row.code} — ${row.title}`, body: UI.loading(), wide: true })
                    try {
                        const { data } = await api(`/subjects/${row.id}`)
                        dialog.body.innerHTML = `<p>${UI.badge(`${data.units} units`, "muted")} ${UI.badge(data.course_code, "muted")}</p>` +
                            (data.sections.length ? UI.table([
                                { label: "Section", value: r => r.section_code },
                                { label: "Days", value: r => UI.days(r.pattern) },
                                { label: "Time", value: r => UI.timeRange(r) },
                                { label: "Instructor", value: r => r.instructor_name || "TBA" },
                                { label: "Room", value: r => r.room_code || "TBA" },
                                { label: "Slots", html: r => UI.seats(r) },
                            ], data.sections) : UI.empty("No class sections scheduled for this subject yet."))
                    } catch (err) {
                        dialog.body.innerHTML = UI.errorState(err.message)
                    }
                }
            },
        })

        const openForm = subject => UI.formDialog({
            title: subject ? "Edit Subject" : "Add Subject",
            fields: [
                { name: "code", label: "Subject code", required: true, minlength: 2, maxlength: 20 },
                { name: "units", label: "Academic units", type: "select", required: true, numeric: true,
                  options: [{ value: 2, label: "2 units" }, { value: 3, label: "3 units" }] },
                { name: "title", label: "Descriptive title", required: true, minlength: 2, maxlength: 200, full: true },
                { name: "course_id", label: "Course", type: "select", required: true, numeric: true,
                  options: UI.options(courses, "id", c => `${c.code} — ${c.name}`) },
            ],
            values: subject || {},
            async onSubmit(body) {
                const res = subject
                    ? await api(`/subjects/${subject.id}`, { method: "PUT", body })
                    : await api("/subjects/", { method: "POST", body })
                UI.toast(res.message)
                load()
            },
        })

        async function load() {
            try {
                list.setRows((await api("/subjects/")).data)
            } catch (err) {
                UI.toast(err.message, "error")
            }
        }

        el.querySelector("[data-add]")?.addEventListener("click", () => openForm(null))
    },
})

// Students enrolled in a subject (for instructors: only their own sections),
// with search, section and year filters, and pagination.
async function showSubjectStudents(subject) {
    const dialog = UI.openDialog({ title: `${subject.code} — enrolled students`, body: UI.loading(), wide: true })
    let students
    try {
        students = (await api(`/subjects/${subject.id}/students`)).data
    } catch (err) {
        dialog.body.innerHTML = UI.errorState(err.message)
        return
    }
    const sections = [...new Map(students.map(s => [s.section_id, s])).values()]
        .sort((a, b) => a.section_code.localeCompare(b.section_code))
    const years = [...new Set(students.map(s => s.year_level).filter(Boolean))].sort()
    dialog.body.innerHTML = `<p><strong>${UI.esc(subject.title)}</strong> · ${UI.badge(`${students.length} enrolled`, "muted")}</p><div data-students></div>`
    UI.listView(dialog.body.querySelector("[data-students]"), {
        rows: students,
        idKey: "enrollment_id",
        search: { placeholder: "Search by name, student ID or email…", text: s => `${s.name} ${s.student_number} ${s.email || ""}` },
        filters: [
            { label: "All sections", options: sections.map(s => ({ value: s.section_id, label: `Section ${s.section_code} · ${UI.slotText(s)}` })),
              match: (s, v) => String(s.section_id) === v },
            ...(years.length ? [{ label: "All year levels", options: years.map(y => ({ value: y, label: `Year ${y}` })),
                                  match: (s, v) => String(s.year_level) === v }] : []),
        ],
        columns: [
            { label: "Student ID", value: s => s.student_number },
            { label: "Name", value: s => s.name },
            { label: "Email", value: s => s.email || "" },
            { label: "Year", value: s => s.year_level ? `Year ${s.year_level}` : "" },
            { label: "Section", value: s => s.section_code },
            { label: "Schedule", value: s => UI.slotText(s) },
            { label: "Room", value: s => s.room_code || "TBA" },
        ],
        emptyText: "No students are enrolled in this subject yet.",
    })
}
