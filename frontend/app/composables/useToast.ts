const toast = reactive({ visible: false, text: '' })
let timer: ReturnType<typeof setTimeout> | undefined

export function useToast() {
  function show(text: string, duration = 3500) {
    toast.text = text
    toast.visible = true
    clearTimeout(timer)
    timer = setTimeout(() => {
      toast.visible = false
    }, duration)
  }
  return { toast, show }
}
