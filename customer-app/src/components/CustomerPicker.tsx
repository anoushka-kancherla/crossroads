import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import { useCustomer } from "../CustomerContext";
import { QueryState } from "./QueryState";

/** The "Demo customer" picker: a stand-in for a real customer sign-in (FR-029). The list holds only
 *  each customer's name and vehicle; their details load once one is selected (FR-028). */
export function CustomerPicker() {
  const { customerId, setCustomerId } = useCustomer();
  const customers = useQuery({ queryKey: ["customers"], queryFn: api.customers });
  const list = customers.data;

  useEffect(() => {
    if (list && list.length > 0 && !list.some((c) => c.id === customerId)) setCustomerId(list[0].id);
  }, [list, customerId, setCustomerId]);

  return (
    <div className="picker">
      <label htmlFor="demo-customer">Demo customer</label>
      <QueryState
        status={customers.status}
        error={customers.error}
        data={list}
        isEmpty={(d) => d.length === 0}
        emptyMessage="No demo customers are available."
      >
        {(items) => (
          <select id="demo-customer" value={customerId ?? ""} onChange={(e) => setCustomerId(e.target.value)}>
            {items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name} · {c.vehicle_label}
              </option>
            ))}
          </select>
        )}
      </QueryState>
    </div>
  );
}
