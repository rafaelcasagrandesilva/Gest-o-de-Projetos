/**
 * Exibida quando o usuário não tem permissão para NENHUMA tela do Workspace atual.
 * (A navegação inicial só cai aqui quando `resolveWorkspaceLanding` retorna null.)
 */
export function WorkspaceNoAccess() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center p-6">
      <div className="max-w-md rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Sem permissão</h2>
        <p className="mt-2 text-sm text-slate-500">
          Você não tem acesso a nenhuma tela deste espaço de trabalho. Fale com um administrador se
          precisar de acesso.
        </p>
      </div>
    </div>
  );
}
