Pages.push({
    id: "subjects",
    nav: "Subjects",
    title: "Subject Management",
    visible: () => Auth.can("subjects.view"),

    async render(el) {
        const courses = (await api("/courses/")).data
        const canManage = Auth.can("subjects.manage")
        el.innerHTML = `<div class="page-actions">${canManage ? '<button type="button" class="btn btn-primary" data-add>Add subject</button>' : ""}</div><div data-list></div>`
        const list = UI.listView(el.querySelector("[data-list]"), {
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
                { label: "Sections", value: r => r.section_count, num: true },
            ],
            actions: r => UI.button("view", r.id, "Sections") +
                (canManage ? UI.button("edit", r.id, "Edit", "edit") + UI.button("delete", r.id, "Delete", "danger") : ""),
            emptyText: "No subjects yet.",
            onAction: async (action, row) => {
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
        await load()
    },
})
