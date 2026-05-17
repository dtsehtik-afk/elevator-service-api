import client from './client'
import type { Part } from '../types'

export interface Warehouse {
  id: string
  name: string
  warehouse_type: 'MAIN' | 'VEHICLE' | 'LAB' | 'EXTERNAL'
  is_active: boolean
  address?: string
  technician_id?: string
  technician_name?: string
}

export interface StockItem {
  part_id: string
  part_name: string
  part_sku?: string
  category?: string
  quantity: number
  min_quantity: number
  is_low_stock: boolean
  unit: string
}

export interface InventoryTransaction {
  id: string
  transaction_type: string
  quantity: number
  unit_price?: number
  reference_number?: string
  notes?: string
  date: string
  part_name?: string
  source_warehouse_name?: string
  target_warehouse_name?: string
}

export const inventoryApi = {
  list: (params?: { search?: string; category?: string; low_stock?: boolean; is_active?: boolean; skip?: number; limit?: number }) =>
    client.get<Part[]>('/inventory', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Part>(`/inventory/${id}`).then(r => r.data),

  create: (data: Partial<Part>) =>
    client.post<Part>('/inventory', data).then(r => r.data),

  update: (id: string, data: Partial<Part>) =>
    client.patch<Part>(`/inventory/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/inventory/${id}`),

  adjustStock: (id: string, delta: number) =>
    client.patch<{ part_id: string; new_quantity: number; is_low_stock: boolean }>(`/inventory/${id}/adjust-stock`, null, { params: { delta } }).then(r => r.data),

  categories: () =>
    client.get<string[]>('/inventory/categories').then(r => r.data),

  recordUsage: (data: { part_id: string; service_call_id?: string; quantity: number; notes?: string }) =>
    client.post('/inventory/usage', data).then(r => r.data),

  usageByCall: (serviceCallId: string) =>
    client.get(`/inventory/usage/by-call/${serviceCallId}`).then(r => r.data),

  // Warehouses
  listWarehouses: (includeInactive = false) =>
    client.get<Warehouse[]>('/inventory/warehouses/list', { params: { include_inactive: includeInactive } }).then(r => r.data),

  createWarehouse: (data: { name: string; warehouse_type: string; address?: string; technician_id?: string }) =>
    client.post<Warehouse>('/inventory/warehouses', data).then(r => r.data),

  updateWarehouse: (id: string, data: Partial<Warehouse>) =>
    client.patch<Warehouse>(`/inventory/warehouses/${id}`, data).then(r => r.data),

  getWarehouseStock: (warehouseId: string, params?: { search?: string; category?: string; low_stock_only?: boolean }) =>
    client.get<StockItem[]>(`/inventory/warehouses/${warehouseId}/stock`, { params }).then(r => r.data),

  // Stock operations
  receiveStock: (data: { part_id: string; warehouse_id: string; quantity: number; unit_price?: number; reference_number?: string; notes?: string }) =>
    client.post('/inventory/stock/receive', data).then(r => r.data),

  transferStock: (data: { part_id: string; source_warehouse_id: string; target_warehouse_id: string; quantity: number; notes?: string }) =>
    client.post('/inventory/stock/transfer', data).then(r => r.data),

  issueStock: (data: { part_id: string; warehouse_id: string; quantity: number; service_call_id?: string; notes?: string }) =>
    client.post('/inventory/stock/issue', data).then(r => r.data),

  listTransactions: (params?: { part_id?: string; warehouse_id?: string; transaction_type?: string; limit?: number }) =>
    client.get<InventoryTransaction[]>('/inventory/transactions', { params }).then(r => r.data),
}
