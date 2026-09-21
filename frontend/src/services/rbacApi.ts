import { api } from '@/services/api'
import type { PermissionMatrix, RolePermissionCell, Role, User } from '@/types'

export function fetchUsers() {
  return api.get<User[]>('/users').then((r) => r.data)
}

export function createUser(payload: {
  email: string
  password: string
  full_name: string
  role_ids: string[]
}) {
  return api.post<User>('/users', payload).then((r) => r.data)
}

export function updateUser(
  id: string,
  payload: Partial<{ full_name: string; is_active: boolean; role_ids: string[] }>,
) {
  return api.patch<User>(`/users/${id}`, payload).then((r) => r.data)
}

export function resetUserPassword(id: string, password: string) {
  return api.put(`/users/${id}/password`, { password })
}

export function deleteUser(id: string) {
  return api.delete(`/users/${id}`)
}

export function fetchRoles() {
  return api.get<Role[]>('/rbac/roles').then((r) => r.data)
}

export function fetchMatrix() {
  return api.get<PermissionMatrix>('/rbac/matrix').then((r) => r.data)
}

export function updateRoleGrants(roleId: string, grants: RolePermissionCell[]) {
  return api.put<PermissionMatrix>('/rbac/matrix', { role_id: roleId, grants }).then((r) => r.data)
}
