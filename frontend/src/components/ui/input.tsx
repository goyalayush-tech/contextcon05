import * as React from "react"
import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "min-h-9 w-full min-w-0 border border-border bg-secondary px-2.5 py-1.5 text-sm outline-none caret-primary transition-colors placeholder:text-muted-foreground hover:border-foreground/45 focus-visible:border-primary disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Input }
