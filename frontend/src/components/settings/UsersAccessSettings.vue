<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import * as rbacApi from '@/services/rbacApi'
import { extractApiErrorMessage } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { PermissionMatrix, Role, User } from '@/types'

const { t } = useI18n()
const authStore = useAuthStore()
const canAdminister = computed(() => authStore.can('ADMINISTRATION', 'ADMIN'))
const canEditUsers = computed(() => authStore.can('ADMINISTRATION', 'EDIT') || canAdminister.value)
const canCreateUsers = computed(() => authStore.can('ADMINISTRATION', 'CREATE') || canAdminister.value)
const canDeleteUsers = computed(() => authStore.can('ADMINISTRATION', 'DELETE') || canAdminister.value)

// --- Users ---
const users = ref<User[]>([])
const roles = ref<Role[]>([])
const usersLoading = ref(true)
const userDialog = ref(false)
const passwordDialog = ref(false)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)

const userForm = reactive({
  id: '' as string | null,
  email: '',
  full_name: '',
  password: '',
  role_id: '' as string,
  is_active: true,
})
const passwordForm = reactive({ id: '', password: '' })

const userHeaders = [
  { title: t('settings.usersAccess.email'), key: 'email' },
  { title: t('settings.usersAccess.fullName'), key: 'full_name' },
  { title: t('settings.usersAccess.role'), key: 'role' },
  { title: t('settings.usersAccess.activeStatus'), key: 'is_active' },
  { title: '', key: 'actions', sortable: false },
]

async function loadUsers(): Promise<void> {
  usersLoading.value = true
  try {
    const [u, r] = await Promise.all([rbacApi.fetchUsers(), rbacApi.fetchRoles()])
    users.value = u
    roles.value = r
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  } finally {
    usersLoading.value = false
  }
}

function openCreateUser(): void {
  userForm.id = null
  userForm.email = ''
  userForm.full_name = ''
  userForm.password = ''
  userForm.role_id = roles.value.find((r) => r.code === 'VIEWER')?.id ?? roles.value[0]?.id ?? ''
  userForm.is_active = true
  userDialog.value = true
}

function openEditUser(user: User): void {
  userForm.id = user.id
  userForm.email = user.email
  userForm.full_name = user.full_name
  userForm.password = ''
  userForm.role_id = user.roles[0]?.id ?? ''
  userForm.is_active = user.is_active
  userDialog.value = true
}

async function saveUser(): Promise<void> {
  errorMessage.value = null
  try {
    if (userForm.id) {
      await rbacApi.updateUser(userForm.id, {
        full_name: userForm.full_name,
        is_active: userForm.is_active,
        role_ids: userForm.role_id ? [userForm.role_id] : [],
      })
    } else {
      await rbacApi.createUser({
        email: userForm.email,
        password: userForm.password,
        full_name: userForm.full_name,
        role_ids: userForm.role_id ? [userForm.role_id] : [],
      })
    }
    userDialog.value = false
    successMessage.value = t('settings.saved')
    await loadUsers()
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  }
}

function openResetPassword(user: User): void {
  passwordForm.id = user.id
  passwordForm.password = ''
  passwordDialog.value = true
}

async function submitResetPassword(): Promise<void> {
  try {
    await rbacApi.resetUserPassword(passwordForm.id, passwordForm.password)
    passwordDialog.value = false
    successMessage.value = t('settings.saved')
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  }
}

async function removeUser(user: User): Promise<void> {
  try {
    await rbacApi.deleteUser(user.id)
    await loadUsers()
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('settings.usersAccess.cannotDeleteSelf'))
  }
}

// --- Permission matrix ---
const matrix = ref<PermissionMatrix | null>(null)
const matrixLoading = ref(true)
const matrixSaving = ref(false)
const selectedRoleId = ref<string>('')
const localGrants = ref<Set<string>>(new Set())

function cellKey(moduleId: string, permissionId: string): string {
  return `${moduleId}:${permissionId}`
}

async function loadMatrix(): Promise<void> {
  matrixLoading.value = true
  try {
    matrix.value = await rbacApi.fetchMatrix()
    if (!selectedRoleId.value) selectedRoleId.value = matrix.value.roles[0]?.id ?? ''
    syncLocalGrants()
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  } finally {
    matrixLoading.value = false
  }
}

function syncLocalGrants(): void {
  if (!matrix.value) return
  const set = new Set<string>()
  matrix.value.grants
    .filter((g) => g.role_id === selectedRoleId.value)
    .forEach((g) => set.add(cellKey(g.module_id, g.permission_id)))
  localGrants.value = set
}

function isGranted(moduleId: string, permissionId: string): boolean {
  return localGrants.value.has(cellKey(moduleId, permissionId))
}

function toggleGrant(moduleId: string, permissionId: string): void {
  const key = cellKey(moduleId, permissionId)
  const next = new Set(localGrants.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  localGrants.value = next
}

async function saveMatrix(): Promise<void> {
  if (!matrix.value) return
  matrixSaving.value = true
  errorMessage.value = null
  try {
    const grants = Array.from(localGrants.value).map((key) => {
      const [moduleId, permissionId] = key.split(':')
      return { role_id: selectedRoleId.value, module_id: moduleId, permission_id: permissionId }
    })
    matrix.value = await rbacApi.updateRoleGrants(selectedRoleId.value, grants)
    syncLocalGrants()
    successMessage.value = t('settings.saved')
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  } finally {
    matrixSaving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadMatrix()])
})
</script>

<template>
  <div>
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3"
    >
      {{ errorMessage }}
    </v-alert>
    <v-alert
      v-if="successMessage"
      type="success"
      variant="tonal"
      density="compact"
      class="mb-3"
      closable
      @click:close="successMessage = null"
    >
      {{ successMessage }}
    </v-alert>

    <v-card
      variant="flat"
      border
      class="mb-4"
    >
      <v-card-item>
        <v-card-title class="text-subtitle-1 font-weight-bold">
          {{ t('settings.usersAccess.users') }}
        </v-card-title>
        <template
          v-if="canCreateUsers"
          #append
        >
          <v-btn
            color="primary"
            size="small"
            prepend-icon="mdi-plus"
            @click="openCreateUser"
          >
            {{ t('settings.usersAccess.addUser') }}
          </v-btn>
        </template>
      </v-card-item>
      <v-data-table
        :headers="userHeaders"
        :items="users"
        :loading="usersLoading"
        density="comfortable"
      >
        <template #item.role="{ item }">
          <v-chip size="small">
            {{ item.roles[0]?.name ?? '—' }}
          </v-chip>
        </template>
        <template #item.is_active="{ item }">
          <v-icon
            :icon="item.is_active ? 'mdi-check-circle' : 'mdi-close-circle'"
            :color="item.is_active ? 'success' : 'error'"
            size="18"
          />
        </template>
        <template #item.actions="{ item }">
          <v-btn
            v-if="canEditUsers"
            icon="mdi-pencil-outline"
            size="small"
            variant="text"
            @click="openEditUser(item)"
          />
          <v-btn
            v-if="canEditUsers"
            icon="mdi-key-outline"
            size="small"
            variant="text"
            @click="openResetPassword(item)"
          />
          <v-btn
            v-if="canDeleteUsers"
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            color="error"
            @click="removeUser(item)"
          />
        </template>
      </v-data-table>
    </v-card>

    <v-card
      variant="flat"
      border
    >
      <v-card-item>
        <v-card-title class="text-subtitle-1 font-weight-bold">
          {{ t('settings.usersAccess.permissionMatrix') }}
        </v-card-title>
        <v-card-subtitle>{{ t('settings.usersAccess.matrixHint') }}</v-card-subtitle>
      </v-card-item>
      <v-card-text>
        <div
          v-if="matrixLoading"
          class="d-flex justify-center py-6"
        >
          <v-progress-circular
            indeterminate
            color="primary"
          />
        </div>
        <template v-else-if="matrix">
          <v-tabs
            v-model="selectedRoleId"
            density="compact"
            class="mb-4"
            @update:model-value="syncLocalGrants"
          >
            <v-tab
              v-for="role in matrix.roles"
              :key="role.id"
              :value="role.id"
            >
              {{ role.name }}
            </v-tab>
          </v-tabs>

          <v-table density="compact">
            <thead>
              <tr>
                <th>{{ t('nav.dashboard') }}</th>
                <th
                  v-for="perm in matrix.permissions"
                  :key="perm.id"
                  class="text-center"
                >
                  {{ perm.code }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="mod in matrix.modules"
                :key="mod.id"
              >
                <td>{{ mod.name }}</td>
                <td
                  v-for="perm in matrix.permissions"
                  :key="perm.id"
                  class="text-center"
                >
                  <v-checkbox-btn
                    :model-value="isGranted(mod.id, perm.id)"
                    :disabled="!canAdminister"
                    @update:model-value="toggleGrant(mod.id, perm.id)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </template>
      </v-card-text>
      <v-card-actions v-if="canAdminister">
        <v-spacer />
        <v-btn
          color="primary"
          :loading="matrixSaving"
          @click="saveMatrix"
        >
          {{ t('common.actions.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <v-dialog
      v-model="userDialog"
      max-width="480"
    >
      <v-card>
        <v-card-title>{{ userForm.id ? t('common.actions.edit') : t('settings.usersAccess.addUser') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="userForm.email"
            :label="t('settings.usersAccess.email')"
            :disabled="Boolean(userForm.id)"
            class="mb-2"
          />
          <v-text-field
            v-model="userForm.full_name"
            :label="t('settings.usersAccess.fullName')"
            class="mb-2"
          />
          <v-text-field
            v-if="!userForm.id"
            v-model="userForm.password"
            type="password"
            label="Password"
            autocomplete="new-password"
            class="mb-2"
          />
          <v-select
            v-model="userForm.role_id"
            :items="roles"
            item-title="name"
            item-value="id"
            :label="t('settings.usersAccess.role')"
            class="mb-2"
          />
          <v-switch
            v-model="userForm.is_active"
            :label="t('settings.usersAccess.activeStatus')"
            color="primary"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            variant="text"
            @click="userDialog = false"
          >
            {{ t('common.actions.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            @click="saveUser"
          >
            {{ t('common.actions.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog
      v-model="passwordDialog"
      max-width="420"
    >
      <v-card>
        <v-card-title>{{ t('settings.usersAccess.resetPassword') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="passwordForm.password"
            type="password"
            autocomplete="new-password"
            label="New password"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            variant="text"
            @click="passwordDialog = false"
          >
            {{ t('common.actions.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            @click="submitResetPassword"
          >
            {{ t('common.actions.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
