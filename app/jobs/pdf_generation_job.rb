class PdfGenerationJob < ApplicationJob
  queue_as :default

  def perform(pdf_result_id)
    pdf_result = PdfResult.find(pdf_result_id)
    filename = "output_#{SecureRandom.hex(8)}.pdf"
    pdf_result.update(filename: filename, generation_state: "generating")

    Puppeteer.launch(headless: true, args: [ "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--no-zygote" ]) do |browser|
      page = browser.new_page
      page.goto(ENV.fetch("PDF_GENERATION_URL"))
      page.pdf(path: "tmp/#{filename}", print_background: true, prefer_css_page_size: true, margin: { top: "0.5in", right: "0.5in", bottom: "0.5in", left: "0.5in" })
      page.close
    end

    pdf_result.update(generation_state: "completed")
    Turbo::StreamsChannel.broadcast_replace_to("pdf_results", target: "pdf_result_#{pdf_result.id}", partial: "home/pdf_result", locals: { pdf_result: pdf_result })

  rescue StandardError => e
    pdf_result.update(generation_state: "failed", error_message: e.message)
    Turbo::StreamsChannel.broadcast_replace_to("pdf_results", target: "pdf_result_#{pdf_result.id}", partial: "home/pdf_result", locals: { pdf_result: pdf_result })
  end
end
