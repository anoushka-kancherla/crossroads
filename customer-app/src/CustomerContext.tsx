import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type CustomerState = { customerId: string | null; setCustomerId: (id: string) => void };

const CustomerContext = createContext<CustomerState | null>(null);
const KEY = "crossroads.customer";

function remembered(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null; // storage can be blocked; the choice just isn't remembered
  }
}

/** The selected demo customer, shared by every screen. In production this would be the signed-in
 *  customer's own account. */
export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customerId, setId] = useState<string | null>(remembered);
  const setCustomerId = useCallback((id: string) => {
    setId(id);
    try {
      sessionStorage.setItem(KEY, id);
    } catch {
      // not remembered, and that is fine
    }
  }, []);
  const value = useMemo(() => ({ customerId, setCustomerId }), [customerId, setCustomerId]);
  return <CustomerContext.Provider value={value}>{children}</CustomerContext.Provider>;
}

export function useCustomer(): CustomerState {
  const value = useContext(CustomerContext);
  if (value === null) throw new Error("useCustomer needs a CustomerProvider");
  return value;
}
