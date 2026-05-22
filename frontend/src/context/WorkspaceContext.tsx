import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type WorkspaceName = "projects" | "finance" | "assets";

const STORAGE_KEY = "sgp_workspace";

function readStoredWorkspace(): WorkspaceName {
  const v = (localStorage.getItem(STORAGE_KEY) ?? "").toLowerCase();
  if (v === "finance") return "finance";
  if (v === "assets") return "assets";
  return "projects";
}

function writeStoredWorkspace(w: WorkspaceName): void {
  localStorage.setItem(STORAGE_KEY, w);
}

type WorkspaceContextValue = {
  workspace: WorkspaceName;
  setWorkspace: (w: WorkspaceName) => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [workspace, setWorkspaceState] = useState<WorkspaceName>(() => readStoredWorkspace());

  useEffect(() => {
    writeStoredWorkspace(workspace);
  }, [workspace]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      workspace,
      setWorkspace: (w) => setWorkspaceState(w),
    }),
    [workspace],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace deve ser usado dentro de WorkspaceProvider");
  return ctx;
}

export function getStoredWorkspaceForApi(): WorkspaceName {
  // Usado fora de React (axios interceptor).
  try {
    return readStoredWorkspace();
  } catch {
    return "finance";
  }
}

