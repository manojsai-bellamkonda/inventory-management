<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="budget-row">
        <label class="budget-label" for="budget-slider">{{ t('restocking.budgetLabel') }}</label>
        <span class="budget-value">{{ formatCurrency(budget, currentCurrency) }}</span>
      </div>
      <input
        id="budget-slider"
        type="range"
        class="budget-slider"
        v-model.number="budget"
        :min="BUDGET_MIN"
        :max="BUDGET_MAX"
        :step="BUDGET_STEP"
      />

      <div class="budget-summary" v-if="!loading && !error">
        <div class="summary-item">
          <div class="summary-label">{{ t('restocking.totalCost') }}</div>
          <div class="summary-value">{{ formatCurrency(totalEstimatedCost, currentCurrency) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="summary-value" :class="{ 'over-budget': remainingBudget < 0 }">
            {{ formatCurrency(remainingBudget, currentCurrency) }}
          </div>
        </div>
        <div class="summary-item" v-if="remainingBudget < 0">
          <span class="badge danger">{{ t('restocking.overBudget') }}</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ recommendations.length }})</h3>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.suggestedQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>
                  {{ item.item_name }}
                  <span v-if="item.is_urgent" class="badge danger urgent-badge">{{ t('restocking.urgent') }}</span>
                </td>
                <td>
                  <span :class="['badge', item.trend]">{{ item.trend }}</span>
                </td>
                <td>{{ item.suggested_quantity }}</td>
                <td>{{ formatCurrency(item.unit_cost, currentCurrency) }}</td>
                <td><strong>{{ formatCurrency(item.estimated_cost, currentCurrency) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-actions">
          <button
            class="btn-primary"
            :disabled="submitting || recommendations.length === 0"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="successMessage" class="success-banner">{{ successMessage }}</div>
        <div v-if="submitError" class="error">{{ submitError }}</div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency.js'

const BUDGET_MIN = 1000
const BUDGET_MAX = 50000
const BUDGET_STEP = 500

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()

    const budget = ref(10000)
    const recommendations = ref([])
    const totalEstimatedCost = ref(0)
    const remainingBudget = ref(0)

    const loading = ref(true)
    const error = ref(null)

    const submitting = ref(false)
    const submitError = ref(null)
    const successMessage = ref(null)

    const formatDeliveryDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        const data = await api.getRestockRecommendations(budget.value)
        recommendations.value = data.recommendations
        totalEstimatedCost.value = data.total_estimated_cost
        remainingBudget.value = data.remaining_budget
      } catch (err) {
        error.value = t('restocking.loadError')
        console.error('Load error:', err)
      } finally {
        loading.value = false
      }
    }

    // Manual debounce on budget changes (no @vueuse/core dependency available)
    let debounceTimer = null
    watch(budget, () => {
      successMessage.value = null
      submitError.value = null
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadRecommendations()
      }, 400)
    })

    onUnmounted(() => clearTimeout(debounceTimer))

    const placeOrder = async () => {
      submitting.value = true
      submitError.value = null
      successMessage.value = null
      try {
        const orderData = {
          items: recommendations.value.map(r => ({
            sku: r.item_sku,
            quantity: r.suggested_quantity
          }))
        }
        const order = await api.submitRestockOrder(orderData)
        successMessage.value = t('restocking.successMessage', {
          orderNumber: order.order_number,
          expectedDelivery: formatDeliveryDate(order.expected_delivery)
        })
        await loadRecommendations()
      } catch (err) {
        submitError.value = t('restocking.errorMessage')
        console.error('Submit error:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    return {
      t,
      currentCurrency,
      formatCurrency,
      budget,
      BUDGET_MIN,
      BUDGET_MAX,
      BUDGET_STEP,
      recommendations,
      totalEstimatedCost,
      remainingBudget,
      loading,
      error,
      submitting,
      submitError,
      successMessage,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.budget-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.budget-label {
  font-size: 0.938rem;
  font-weight: 600;
  color: #334155;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

/* Cross-browser range slider styling */
.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-runnable-track {
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  cursor: pointer;
  margin-top: -6px;
}

.budget-slider::-moz-range-track {
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
}

.budget-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  cursor: pointer;
}

.budget-summary {
  display: flex;
  gap: 2rem;
  align-items: center;
  padding-top: 0.75rem;
  border-top: 1px solid #f1f5f9;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.summary-value.over-budget {
  color: #dc2626;
}

.urgent-badge {
  margin-left: 0.5rem;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}

.order-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.25rem;
}

.btn-primary {
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 0.625rem 1.5rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

.success-banner {
  margin-top: 1rem;
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #a7f3d0;
  padding: 1rem;
  border-radius: 8px;
  font-size: 0.938rem;
}
</style>
