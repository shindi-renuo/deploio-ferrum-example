class HomeController < ApplicationController
  def index
  end

  def generate_pdf
    browser = Ferrum::Browser.new(headless: true, timeout: 20)
    browser.go_to("http://localhost:3000/example")
    browser.pdf(path: "example.pdf", paper_width: 1.0, paper_height: 1.0)
    browser.quit()
    send_file "example.pdf", filename: "example.pdf", type: "application/pdf"
  end
end
