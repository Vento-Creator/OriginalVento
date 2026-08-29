import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

// Telegram WebApp initData
function getInitData() {
  if (typeof window !== 'undefined' && window.Telegram?.WebApp?.initData) {
    return window.Telegram.WebApp.initData
  }
  // Dev mode fallback
  return import.meta.env.VITE_DEV_INIT_DATA || ''
}

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

// Har bir so'rovda initData headerini qo'shish
api.interceptors.request.use((config) => {
  const initData = getInitData()
  if (initData) {
    config.headers['X-Init-Data'] = initData
  }
  return config
})

export const usersApi = {
  getMe: () => api.get('/users/me'),
}

export const subscriptionApi = {
  get: () => api.get('/subscription/'),
  getHistory: () => api.get('/subscription/history'),
  createInvoice: () => api.post('/subscription/pay'),
}

export const commandsApi = {
  get: () => api.get('/commands/'),
  update: (command, value) => api.put('/commands/', { command, value }),
  reset: (command) => api.delete(`/commands/${command}`),
}

export const adminApi = {
  getUsers: (page = 1, limit = 20) => api.get(`/admin/users?page=${page}&limit=${limit}`),
  getStats: () => api.get('/admin/stats'),
  getPending: () => api.get('/admin/pending'),
}

export const statsApi = {
  get: () => api.get('/stats/'),
}

export default api
