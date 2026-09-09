export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuth()

  if (to.path === '/login') {
    if (auth.isAuthenticated.value) return navigateTo('/dashboard')
    return
  }

  if (!auth.isAuthenticated.value) {
    return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  }

  // El rol visor (viewer) no puede capturar: solo lectura.
  if (to.path.startsWith('/chat') && !auth.canCapture.value) {
    useToast().show('Solo lectura')
    return navigateTo('/dashboard')
  }

  if (to.path.startsWith('/admin') && !auth.isAdmin.value) {
    useToast().show('No tienes permisos de administración')
    return navigateTo('/dashboard')
  }
})
