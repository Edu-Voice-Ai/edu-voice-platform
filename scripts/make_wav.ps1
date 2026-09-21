Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToWaveFile("c:\Anti Gravity\P-1\handoff_test.wav")
$synth.Speak("I want to talk to a human.")
$synth.Dispose()
Write-Host "Done, size:" (Get-Item "c:\Anti Gravity\P-1\handoff_test.wav").Length
