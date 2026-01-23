import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"

export function FAQ() {
  const faqs = [
    {
      question: "Is this legal under FAA rules?",
      answer:
        "Pico balloons under 6 pounds (including payload) are exempt from FAA notification requirements under 14 CFR Part 101. We follow all applicable regulations and coordinate with relevant authorities for larger deployments.",
    },
    {
      question: "What about international drift?",
      answer:
        "Balloons may drift across international boundaries. We maintain transparency with partner agencies, follow ICAO guidelines, and design payloads to minimize environmental impact. Coordination protocols are established for cross-border operations.",
    },
    {
      question: "How do you ensure environmental safety?",
      answer:
        "All components are selected to minimize ecological impact. Payloads use biodegradable or recoverable materials where possible. We conduct environmental impact assessments and follow best practices for atmospheric research.",
    },
    {
      question: "What sensors are included?",
      answer:
        "Standard configuration includes pressure, temperature, and humidity sensors. Optional modules include GPS for position tracking, wind speed estimation, and additional atmospheric chemistry sensors depending on mission requirements.",
    },
    {
      question: "How is data quality validated?",
      answer:
        "Data undergoes multi-stage validation: sensor calibration against NIST-traceable standards, comparison with radiosonde observations, cross-validation with reanalysis datasets, and peer review of processing algorithms. All QA/QC procedures are documented.",
    },
    {
      question: "Is data open by default?",
      answer:
        "Yes. All datasets are published under permissive open licenses (CC BY 4.0 or similar) with complete metadata. Processing code is open source. We believe open data accelerates scientific progress and builds public trust.",
    },
  ]

  return (
    <section id="faq" className="border-b border-slate-200 bg-slate-50 py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
            Frequently Asked Questions
          </h2>
        </div>
        <div className="mx-auto mt-12 max-w-3xl">
          <Accordion type="single" collapsible className="w-full">
            {faqs.map((faq, index) => (
              <AccordionItem key={index} value={`item-${index}`} className="border-slate-200">
                <AccordionTrigger className="text-left text-slate-900 hover:text-slate-900 hover:no-underline">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-sm leading-relaxed text-slate-600">{faq.answer}</AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  )
}
