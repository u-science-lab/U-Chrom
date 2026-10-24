let agentMutationDepth = 0

/** Run a page mutation that is owned by an approved local agent plan. */
export async function runAsAgentMutation<T>(fn: () => T | Promise<T>): Promise<T> {
  agentMutationDepth += 1
  try {
    return await fn()
  } finally {
    agentMutationDepth -= 1
  }
}

export function agentMutationAllowed(): boolean {
  return agentMutationDepth > 0
}
