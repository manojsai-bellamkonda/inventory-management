import { ref, watch } from 'vue'

const STORAGE_KEY = 'app-theme'

// Load saved theme preference from localStorage, default to light
const savedTheme = localStorage.getItem(STORAGE_KEY)
const isDark = ref(savedTheme === 'dark')

// Apply (or remove) the data-theme attribute on the root <html> element
const applyTheme = (dark) => {
  if (dark) {
    document.documentElement.setAttribute('data-theme', 'dark')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

// Apply immediately on module load so there's no flash of the wrong theme
applyTheme(isDark.value)

export function useDarkMode() {
  const toggleDarkMode = () => {
    isDark.value = !isDark.value
  }

  const setDarkMode = (value) => {
    isDark.value = value
  }

  // Keep DOM attribute + localStorage in sync with state (singleton, shared across app)
  watch(
    isDark,
    (dark) => {
      applyTheme(dark)
      localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
    },
    { immediate: false }
  )

  return {
    isDark,
    toggleDarkMode,
    setDarkMode,
  }
}
