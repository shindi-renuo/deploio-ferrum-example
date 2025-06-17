class HomeController < ApplicationController
  def index
  end

  def generate_pdf
    Puppeteer.launch(headless: true, args: [ "--no-sandbox" ]) do |browser|
      page = browser.new_page
      page.goto("https://arrogant-aurora.941625c.deploio.app/example")
      page.pdf(path: "output.pdf", print_background: true, prefer_css_page_size: true, margin: { top: "0.5in", right: "0.5in", bottom: "0.5in", left: "0.5in" })
      page.close
      send_file "output.pdf", filename: "output.pdf", type: "application/pdf"
    end
  end
end
