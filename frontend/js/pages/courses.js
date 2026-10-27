Pages.push({
    id: "courses",
    nav: "Courses",
    title: "Course Management",
    visible: () => Auth.can("courses.view"),

    async render(el) {
        const { data: courses, min_subjects: minSubjects } = await api("/courses/")
        const canManage = Auth.can("courses.manage")
        el.innerHTML = `
            <p class="muted">The system offers four courses. Each course needs at least ${minSubjects} subjects.
            ${canManage ? "Rename any placeholder course to its official name." : ""}</p>
            <div class="cards">${courses.map(c => `
                <article class="card">
                    <h2>${UI.esc(c.code)}</h2>
                    <p class="card-title">${UI.esc(c.name)}</p>
                    <p class="muted">${UI.esc(c.description) || "No description yet."}</p>
                    <p>${c.meets_subject_minimum ? UI.badge(`${c.subject_count} subjects`) : UI.badge(`${c.subject_count} / ${minSubjects} subjects`, "warn")}
                       ${UI.badge(`${c.student_count} students`, "muted")}</p>
                    <div class="card-actions">
                        ${UI.button("subjects", c.id, "View subjects")}
                        ${canManage ? UI.button("edit", c.id, "Edit", "edit") : ""}
                    </div>
                </article>`).join("")}
            </div>`

        el.querySelector(".cards").addEventListener("click", async e => {
            const btn = e.target.closest("[data-action]")
            if (!btn) return
            const course = courses.find(c => String(c.id) === btn.dataset.id)
            if (btn.dataset.action === "edit") {
                UI.formDialog({
                    title: `Edit ${course.code}`,
                    fields: [
                        { name: "code", label: "Course code", required: true, minlength: 2, maxlength: 20 },
                        { name: "name", label: "Course name", required: true, minlength: 2, maxlength: 150, full: true },
                        { name: "description", label: "Description", type: "textarea", maxlength: 500, full: true },
                    ],
                    values: course,
                    onSubmit: async body => {
                        UI.toast((await api(`/courses/${course.id}`, { method: "PUT", body })).message)
                        this.render(el)
                    },
                })
            }
            if (btn.dataset.action === "subjects") {
                const dialog = UI.openDialog({ title: `${course.code} subjects`, body: UI.loading(), wide: true })
                try {
                    const { data } = await api(`/courses/${course.id}`)
                    dialog.body.innerHTML = data.subjects.length ? UI.table([
                        { label: "Code", value: r => r.code },
                        { label: "Descriptive title", value: r => r.title },
                        { label: "Units", value: r => r.units },
                    ], data.subjects) : UI.empty("No subjects added to this course yet.")
                } catch (err) {
                    dialog.body.innerHTML = UI.errorState(err.message)
                }
            }
        })
    },
})
