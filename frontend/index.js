// App shell: login, role-based navigation and page routing (#/page-id).
document.addEventListener('DOMContentLoaded', () => {
    const loginView = document.getElementById("login-view")
    const appView = document.getElementById("app-view")
    const loginForm = document.getElementById("login-form")
    const loginError = document.getElementById("login-error")
    const nav = document.getElementById("nav")
    const pageEl = document.getElementById("page")
    const titleEl = document.getElementById("page-title")
    const sidebar = document.getElementById("sidebar")
    const scrim = document.getElementById("scrim")
    const menuToggle = document.getElementById("menu-toggle")
    const accountButton = document.getElementById("account-button")
    const accountMenu = document.getElementById("account-menu")

    const ROLE_NAMES = {
        admin: "Administrator", college_admin: "IT Administrator",
        instructor: "Instructor", student: "Student",
    }

    const icon = id => UI.icon(id, "nav-icon")

    // Only pages the user's role is allowed to see appear in the menu
    // (the server enforces the same permissions on every request).
    const visiblePages = () => Pages.filter(page => page.visible())

    function showLogin(message) {
        appView.hidden = true
        loginView.hidden = false
        loginError.hidden = !message
        loginError.textContent = message || ""
        loginForm.elements.username.focus()
    }

    async function start() {
        try {
            Auth.user = (await api("/auth/me")).data
        } catch {
            Auth.clear()
            showLogin()
            return
        }
        loginView.hidden = true
        appView.hidden = false
        document.getElementById("account-name").textContent = Auth.user.username
        document.getElementById("account-role").textContent = ROLE_NAMES[Auth.user.role]
        accountButton.textContent = Auth.user.username.slice(0, 2).toUpperCase()
        accountButton.title = `${Auth.user.username} (${ROLE_NAMES[Auth.user.role]})`
        nav.innerHTML = visiblePages()
            .map(page => `<a href="#/${page.id}" data-page="${page.id}">${icon(page.id)}<span>${UI.esc(page.nav)}</span></a>`).join("")
        route()
    }

    function setDrawer(open) {
        sidebar.classList.toggle("open", open)
        scrim.hidden = !open
        menuToggle.setAttribute("aria-expanded", String(open))
    }

    function setAccountMenu(open) {
        accountMenu.hidden = !open
        accountButton.setAttribute("aria-expanded", String(open))
        if (open) accountMenu.querySelector("[role=menuitem]").focus()
    }

    async function route() {
        if (!Auth.user) return
        const pages = visiblePages()
        const id = location.hash.replace(/^#\//, "")
        const page = pages.find(p => p.id === id) || pages[0]
        nav.querySelectorAll("a").forEach(a => a.toggleAttribute("aria-current", a.dataset.page === page.id))
        titleEl.textContent = page.title
        document.title = `${page.title} · Paulino Dari National High School`
        setDrawer(false)
        pageEl.innerHTML = UI.loading()
        try {
            await page.render(pageEl)
        } catch (err) {
            pageEl.innerHTML = UI.errorState(err.message)
        }
    }

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault()
        const body = Object.fromEntries(new FormData(loginForm))
        const button = loginForm.querySelector("button")
        button.disabled = true
        loginError.hidden = true
        try {
            const result = await api("/auth/login", { method: "POST", body })
            Auth.save(result.token)
            loginForm.reset()
            await start()
        } catch (err) {
            loginError.textContent = err.message
            loginError.hidden = false
        } finally {
            button.disabled = false
        }
    })

    document.getElementById("logout").addEventListener("click", async () => {
        setAccountMenu(false)
        try { await api("/auth/logout", { method: "POST" }) } catch { /* already logged out */ }
        Auth.clear()
        location.hash = ""
        showLogin()
    })

    document.getElementById("change-password").addEventListener("click", () => {
        setAccountMenu(false)
        UI.formDialog({
            title: "Change password",
            fields: [
                { name: "current_password", label: "Current password", type: "password", required: true, autocomplete: "current-password" },
                { name: "new_password", label: "New password (min 8 characters)", type: "password", required: true,
                  minlength: 8, autocomplete: "new-password" },
            ],
            async onSubmit(body) {
                UI.toast((await api("/auth/change-password", { method: "POST", body })).message)
            },
        })
    })

    accountButton.addEventListener("click", () => setAccountMenu(accountMenu.hidden))
    document.addEventListener("click", e => {
        if (!accountMenu.hidden && !e.target.closest(".account")) setAccountMenu(false)
    })
    document.addEventListener("keydown", e => {
        if (e.key !== "Escape") return
        if (!accountMenu.hidden) { setAccountMenu(false); accountButton.focus() }
        if (sidebar.classList.contains("open")) setDrawer(false)
    })
    menuToggle.addEventListener("click", () => setDrawer(!sidebar.classList.contains("open")))
    scrim.addEventListener("click", () => setDrawer(false))

    window.addEventListener("hashchange", route)
    window.addEventListener("auth:expired", () => showLogin("Your session has expired. Please sign in again."))

    if (Auth.token) start()
    else showLogin()
})
