class HomeController < ApplicationController
  def index
  end

  def generate_pdf
    chromium_path = File.expand_path("../chromium-linux/chrome", __dir__)
    browser = Ferrum::Browser.new(browser_path: chromium_path, headless: true)
    browser.go_to("http://localhost:3000/example")
    browser.pdf(path: "example.pdf", paper_width: 1.0, paper_height: 1.0)
    browser.quit()
    send_file "example.pdf", filename: "example.pdf", type: "application/pdf"
  end
end
