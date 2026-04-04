import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ScenarioKind = "PREVISTO" | "REALIZADO";

const ScenarioContext = createContext<{
  globalScenario: ScenarioKind;
  setGlobalScenario: (s: ScenarioKind) => void;
} | null>(null);

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [globalScenario, setGlobalScenarioState] = useState<ScenarioKind>("REALIZADO");
  const setGlobalScenario = useCallback((s: ScenarioKind) => {
    setGlobalScenarioState(s);
  }, []);
  const value = useMemo(
    () => ({ globalScenario, setGlobalScenario }),
    [globalScenario, setGlobalScenario]
  );
  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
}

export function useScenario(): { globalScenario: ScenarioKind; setGlobalScenario: (s: ScenarioKind) => void } {
  const ctx = useContext(ScenarioContext);
  if (!ctx) {
    throw new Error("useScenario must be used within ScenarioProvider");
  }
  return ctx;
}
