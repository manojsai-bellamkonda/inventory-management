<template>
  <button
    class="theme-toggle"
    @click="toggleDarkMode"
    :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
  >
    <svg v-if="isDark" width="18" height="18" viewBox="0 0 20 20" fill="none" class="theme-icon">
      <path
        d="M17 10.5A7 7 0 018.5 3a7 7 0 108.5 7.5z"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <svg v-else width="18" height="18" viewBox="0 0 20 20" fill="none" class="theme-icon">
      <circle cx="10" cy="10" r="3.5" stroke="currentColor" stroke-width="1.5" />
      <path
        d="M10 2.5V4M10 16V17.5M17.5 10H16M4 10H2.5M15.3 4.7L14.2 5.8M5.8 14.2L4.7 15.3M15.3 15.3L14.2 14.2M5.8 5.8L4.7 4.7"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
      />
    </svg>
    <span class="theme-label">{{ isDark ? 'Dark' : 'Light' }}</span>
  </button>
</template>

<script setup>
import { useDarkMode } from '../composables/useDarkMode'

const { isDark, toggleDarkMode } = useDarkMode()
</script>

<style scoped>
.theme-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.875rem;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
  font-size: 0.875rem;
  color: var(--color-text-body);
}

.theme-toggle:hover {
  background: var(--color-bg-surface-alt);
  border-color: var(--color-border-strong);
}

.theme-icon {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.theme-label {
  font-weight: 500;
}
</style>
