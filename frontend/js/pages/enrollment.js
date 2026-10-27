Pages.push({
    id: "enrollment",
    nav: "Enrollment",
    title: "Enrollment Management",
    visible: () => Auth.can("enrollments.view"),

    async render(el) {
        const canManage = Auth.can("enrollments.manage")
        const courses = (await api("/courses/")).data
        el.innerHTML = `<p class="muted">Choose a class section to see its students${canManage ? ", enroll new students or drop enrollments" : ""}.
            Each section holds at most 30 students.</p><div data-list></div>`

        const list = UI.listView(el.querySelector("[data-list]"), {
            search: { placeholder: "Search subject, section, instructor…",
                      text: r => `${r.subject_code} ${r.subject_title} ${r.section_code} ${r.instructor_name || ""}` },
            filters: [
                { label: "All courses", options: UI.options(courses, "id", c => c.code), match: (r, v) => String(r.course_id) === v },
                { label: "Any availability", options: [{ value: "open", label: "Has open slots" }, { value: "full", label: "Full" }],
                  match: (r, v) => (v === "open") === (r.available_slots > 0) },
            ],
            pageSize: 15,
            columns: [
                { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
                { label: "Course", value: r => r.course_code },
                { label: "Section", value: r => r.section_code },
                { label: "Schedule", value: r => UI.slotText(r) },
                { label: "Room", value: r => r.room_code || "TBA" },
                { label: "Enrolled / Available", html: r => UI.seats(r) },
            ],
            actions: r => UI.button("roster", r.id, "Students") +
                (canManage && r.available_slots > 0 ? UI.button("enroll", r.id, "Enroll student", "edit") : ""),
            emptyText: "No class sections scheduled yet.",
            onAction: (action, row) => {
                if (action === "roster") showRoster(row.id, canManage ? { onDrop: load } : {})
                if (action === "enroll") enrollDialog(row)
            },
        })

        async function load() {
            list.setRows((await api("/sections")).data)
        }

        function enrollDialog(section) {
            const dialog = UI.openDialog({
                title: `Enroll in ${section.subject_code} ${section.section_code}`,
                wide: true,
                body: `<p>${UI.esc(UI.slotText(section))} · ${UI.seats(section)}</p>
                    <p class="muted">Only ${UI.esc(section.course_code)} students can enroll in this subject.</p>
                    <input type="search" class="search" placeholder="Search student name or ID…" aria-label="Search students">
                    <div data-results>${UI.empty("Type to search for a student.")}</div>`,
            })
            const results = dialog.body.querySelector("[data-results]")
            let timer
            dialog.body.querySelector("input").addEventListener("input", e => {
                clearTimeout(timer)
                timer = setTimeout(async () => {
                    const q = e.target.value.trim()
                    if (!q) { results.innerHTML = UI.empty("Type to search for a student."); return }
                    results.innerHTML = UI.loading()
                    try {
                        const { data } = await api("/students/", { query: { q, course_id: section.course_id, page_size: 10 } })
                        results.innerHTML = data.length ? UI.table([
                            { label: "Student ID", value: r => r.student_number },
                            { label: "Name", value: r => r.name },
                            { label: "Year", value: r => r.year_level || "" },
                        ], data, r => UI.button("pick", r.id, "Enroll", "primary")) : UI.empty("No matching students in this course.")
                    } catch (err) {
                        results.innerHTML = UI.errorState(err.message)
                    }
                }, 300)
            })
            results.addEventListener("click", async e => {
                const btn = e.target.closest("[data-action=pick]")
                if (!btn) return
                btn.disabled = true
                const ok = await UI.run(() => api("/enrollments/", {
                    method: "POST", body: { student_id: Number(btn.dataset.id), section_id: section.id },
                }))
                btn.disabled = false
                if (ok) { dialog.close(); load() }
            })
            dialog.body.querySelector("input").focus()
        }

        await load()
    },
})

Pages.push({
    id: "my-enrollment",
    nav: "My Enrollment",
    title: "My Enrollment",
    visible: () => Auth.can("self.enroll"),

    async render(el) {
        let me
        try {
            me = (await api("/students/me")).data
        } catch (err) {
            el.innerHTML = UI.empty(err.message)
            return
        }
        const [mine, sections] = await Promise.all([
            api("/enrollments/me"),
            api("/sections", { query: { course_id: me.course_id } }).then(r => r.data),
        ])
        const open = mine.enrollment_enabled
        const takenSubjects = new Set(mine.data.map(e => e.subject_id))
        const units = mine.data.reduce((sum, e) => sum + e.units, 0)

        el.innerHTML = `
            <p>${open ? UI.badge("Enrollment is open") : UI.badge("Enrollment is closed", "warn")}
               You are in <strong>${UI.esc(me.course)}</strong> — ${mine.data.length} class(es), ${units} units.</p>
            <section class="panel"><h2>My classes</h2><div data-mine></div></section>
            <section class="panel"><h2>My weekly schedule</h2>${UI.weekGrid(mine.data)}</section>
            <section class="panel"><h2>Available class sections for ${UI.esc(me.course)}</h2><div data-available></div></section>`

        const reload = () => this.render(el)
        const mineEl = el.querySelector("[data-mine]")
        mineEl.innerHTML = mine.data.length ? UI.table([
            { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
            { label: "Units", value: r => r.units },
            { label: "Section", value: r => r.section_code },
            { label: "Schedule", value: r => UI.slotText(r) },
            { label: "Room", value: r => r.room_code || "TBA" },
            { label: "Instructor", value: r => r.instructor_name || "TBA" },
        ], mine.data, open ? r => UI.button("drop", r.enrollment_id, "Drop", "danger") : null)
            : UI.empty("You are not enrolled in any class yet.")
        mineEl.addEventListener("click", async e => {
            const btn = e.target.closest("[data-action=drop]")
            if (!btn) return
            const row = mine.data.find(r => String(r.enrollment_id) === btn.dataset.id)
            if (await UI.confirmAction(`Drop ${row.subject_code} section ${row.section_code}?`, { confirmText: "Drop" })) {
                if (await UI.run(() => api(`/enrollments/me/${row.enrollment_id}`, { method: "DELETE" }))) reload()
            }
        })

        const clashWith = section => mine.data.find(e => UI.overlaps(section, e))
        UI.listView(el.querySelector("[data-available]"), {
            rows: sections,
            search: { placeholder: "Search subject…", text: r => `${r.subject_code} ${r.subject_title} ${r.instructor_name || ""}` },
            filters: [{ label: "MWF & TTH", options: [{ value: "MWF", label: "MWF" }, { value: "TTH", label: "TTH" }],
                        match: (r, v) => r.pattern === v }],
            columns: [
                { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
                { label: "Units", value: r => r.units },
                { label: "Section", value: r => r.section_code },
                { label: "Schedule", value: r => UI.slotText(r) },
                { label: "Instructor", value: r => r.instructor_name || "TBA" },
                { label: "Room", value: r => r.room_code || "TBA" },
                { label: "Slots", html: r => UI.seats(r) },
            ],
            actions: r => {
                if (takenSubjects.has(r.subject_id)) return UI.badge("Enrolled", "muted")
                if (!open) return ""
                if (r.available_slots <= 0) return UI.badge("Full", "danger")
                const clash = clashWith(r)
                if (clash) return UI.badge(`Conflicts with ${clash.subject_code}`, "warn")
                return UI.button("enroll", r.id, "Enroll", "primary")
            },
            emptyText: "No class sections are scheduled for your course yet.",
            onAction: async (action, row, btn) => {
                btn.disabled = true
                if (await UI.run(() => api("/enrollments/me", { method: "POST", body: { section_id: row.id } }))) reload()
                else btn.disabled = false
            },
        })
    },
})
