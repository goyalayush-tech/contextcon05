import * as React from "react"
import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "min-h-10 w-full min-w-0 rounded-md border border-input bg-card px-3 py-2 text-sm outline-none caret-primary transition-colors placeholder:text-muted-foreground hover:border-foreground/45 focus-visible:border-primary disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Input }
