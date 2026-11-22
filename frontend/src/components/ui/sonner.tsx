import { Toaster as Sonner, type ToasterProps } from 'sonner'

// Modernist toast: square corners, ink border, accent on success. No theme provider needed (light only).
export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: '!rounded-none !border-2 !border-foreground !bg-background !text-foreground !shadow-lg font-sans',
          description: '!text-muted-foreground',
        },
      }}
      {...props}
    />
  )
}
