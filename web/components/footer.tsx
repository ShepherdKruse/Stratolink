import Image from "next/image"

export function Footer() {
  return (
    <footer className="border-t py-12">
      <div className="mx-auto max-w-5xl px-6 sm:px-8">
        <div className="text-center">
          <div className="mb-6 flex justify-center">
            <Image
              src="/stratolink-logo-footer.png"
              alt="Stratolink"
              width={400}
              height={80}
              className="h-12 w-auto opacity-80"
            />
          </div>
          <p className="text-sm font-light leading-relaxed text-muted-foreground">
            Stratolink is building high-altitude atmospheric communications infrastructure for research, education, and
            global connectivity.
          </p>
          <div className="mt-6 text-xs text-muted-foreground">
            <p>&copy; {new Date().getFullYear()} Stratolink. All data published under open licenses.</p>
          </div>
        </div>
      </div>
    </footer>
  )
}
