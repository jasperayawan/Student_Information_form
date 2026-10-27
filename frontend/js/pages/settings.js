Pages.push({
    id: "settings",
    nav: "Settings",
    title: "Scheduling Settings",
    visible: () => Auth.can("settings.view"),

    async render(el) {
        const settings = (await api("/settings")).data
        const canManage = Auth.can("settings.manage")
        const fields = [
            { name: "room_open_time", label: "Rooms open at", type: "time", required: true, section: "Room operating hours" },
            { name: "room_close_time", label: "Rooms close at", type: "time", required: true, section: "Room operating hours",
              help: "The default is an 8-hour window. Confirm the school's actual hours." },
            { name: "mwf_duration_minutes", label: "MWF class length (minutes)", type: "number", required: true,
              min: 15, max: 300, section: "Standard class length" },
            { name: "tth_duration_minutes", label: "TTH class length (minutes)", type: "number", required: true,
              min: 15, max: 300, section: "Standard class length" },
            { name: "student_enrollment_enabled", label: "Allow students to enroll in and drop classes themselves",
              type: "checkbox", full: true, section: "Enrollment" },
        ]

        el.innerHTML = `<section class="panel"><form class="form" data-form>
            ${UI.formHtml(fields.map(f => ({ ...f, disabled: !canManage })), settings)}
            ${canManage
                ? '<p class="form-error" role="alert" hidden></p><div class="dialog-actions"><button type="submit" class="btn btn-primary">Save settings</button></div>'
                : '<p class="muted">You have view-only access to these settings.</p>'}
        </form></section>`

        const form = el.querySelector("[data-form]")
        form.addEventListener("submit", async e => {
            e.preventDefault()
            const errorEl = form.querySelector(".form-error")
            errorEl.hidden = true
            try {
                UI.toast((await api("/settings", { method: "PUT", body: UI.readForm(form, fields) })).message)
            } catch (err) {
                errorEl.textContent = err.message
                errorEl.hidden = false
            }
        })
    },
})
